import * as cdk from "aws-cdk-lib";
import * as path from "path";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import { Construct } from "constructs";
import { DockerFunction } from "./constructs/docker-function";
import { ScheduledScraper } from "./constructs/scheduled-scraper";
import { ScraperWorker } from "./constructs/scraper";

export class InfrastructureStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const projectName = "surf-alerts";
    const codebuildSrcDir = process.env.CODEBUILD_SRC_DIR ?? ".";

    // S3 bucket for storing scraped data
    const dataBucket = new s3.Bucket(this, "DataBucket", {
      bucketName: `${projectName}-data`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      encryption: s3.BucketEncryption.S3_MANAGED,
      eventBridgeEnabled: true,
    });

    // Sitemap scraper - runs daily at 06:00 UTC
    const sitemapScraper = new ScheduledScraper(
      this,
      "SitemapScraperConstruct",
      {
        projectName: projectName,
        scraperName: "sitemap-scraper",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "scrapers",
          "sitemap_scraper",
        ),
        timeout: 60,
        memorySize: 1024,
        schedule: events.Schedule.cron({ hour: "6", minute: "0" }),
        bucket: dataBucket,
      },
    );

    // Spot scraper - SQS triggered, processes individual spots from taxonomy API
    const spotScraper = new ScraperWorker(this, "SpotScraperConstruct", {
      projectName: projectName,
      scraperName: "spot-scraper",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "scrapers",
        "spot_scraper",
      ),
      timeout: 60,
      memorySize: 1024,
      maxConcurrency: 2,
      environment: {
        DATA_BUCKET: dataBucket.bucketName,
      },
    });

    dataBucket.grantReadWrite(spotScraper.lambdaFunction);

    const discoveryDiff = new DockerFunction(this, "DiscoveryDiffConstruct", {
      projectName: projectName,
      functionName: "discovery-diff",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "jobs",
        "discovery_diff",
      ),
      timeout: 120,
      memorySize: 1024,
      environment: {
        DATA_BUCKET: dataBucket.bucketName,
        SPOT_SCRAPER_QUEUE_URL: spotScraper.queue.queueUrl,
      },
    });

    const spotReportProcessor = new DockerFunction(
      this,
      "SpotReportProcessorConstruct",
      {
        projectName: projectName,
        functionName: "spot-report-processor",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "jobs",
          "spot_report_processor",
        ),
        timeout: 120,
        memorySize: 1024,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
        },
      },
    );

    const discoveryCompletion = new DockerFunction(
      this,
      "DiscoveryCompletionConstruct",
      {
        projectName: projectName,
        functionName: "discovery-completion",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "jobs",
          "discovery_completion",
        ),
        timeout: 60,
        memorySize: 512,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
        },
      },
    );

    const catalogBuilder = new DockerFunction(this, "CatalogBuilderConstruct", {
      projectName: projectName,
      functionName: "catalog-builder",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "jobs",
        "catalog_builder",
      ),
      timeout: 180,
      memorySize: 1024,
      environment: {
        DATA_BUCKET: dataBucket.bucketName,
      },
    });

    dataBucket.grantReadWrite(discoveryDiff.lambdaFunction);
    dataBucket.grantReadWrite(spotReportProcessor.lambdaFunction);
    dataBucket.grantReadWrite(discoveryCompletion.lambdaFunction);
    dataBucket.grantReadWrite(catalogBuilder.lambdaFunction);
    spotScraper.queue.grantSendMessages(discoveryDiff.lambdaFunction);

    new events.Rule(this, "DiscoveryDiffRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: { key: [{ prefix: "raw/sitemap/" }] },
        },
      },
      targets: [new targets.LambdaFunction(discoveryDiff.lambdaFunction)],
    });

    new events.Rule(this, "SpotReportProcessorRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: { key: [{ prefix: "raw/spot_report/" }] },
        },
      },
      targets: [new targets.LambdaFunction(spotReportProcessor.lambdaFunction)],
    });

    new events.Rule(this, "DiscoveryCompletionRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: { key: [{ prefix: "control/manifests/discovery_runs/" }] },
        },
      },
      targets: [new targets.LambdaFunction(discoveryCompletion.lambdaFunction)],
    });

    new events.Rule(this, "CatalogBuilderRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: {
            key: [{ prefix: "control/manifests/processing/domain=discovery/" }],
          },
        },
      },
      targets: [new targets.LambdaFunction(catalogBuilder.lambdaFunction)],
    });

    dataBucket.grantReadWrite(sitemapScraper.lambdaFunction);
  }
}
