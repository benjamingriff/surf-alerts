import * as cdk from "aws-cdk-lib";
import * as path from "path";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import { Construct } from "constructs";
import { DockerFunction } from "./constructs/docker-function";
import { ScheduledScraper } from "./constructs/scheduled-scraper";
import { ScraperWorker } from "./constructs/scraper";

export class InfrastructureStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const projectName = "surf-alerts";
    const codebuildSrcDir = process.env.CODEBUILD_SRC_DIR ?? ".";

    const dataBucket = new s3.Bucket(this, "DataBucket", {
      bucketName: `${projectName}-data`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      encryption: s3.BucketEncryption.S3_MANAGED,
      eventBridgeEnabled: true,
    });

    const sitemapScraper = new ScheduledScraper(
      this,
      "SitemapScraperConstruct",
      {
        projectName,
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
        schedule: events.Schedule.cron({
          hour: "6",
          minute: "0",
          weekDay: "MON",
        }),
        bucket: dataBucket,
      },
    );

    const spotScraper = new ScraperWorker(this, "SpotScraperConstruct", {
      projectName,
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

    const discoveryDiff = new DockerFunction(this, "DiscoveryDiffConstruct", {
      projectName,
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

    const discoveryCompletion = new DockerFunction(
      this,
      "DiscoveryCompletionConstruct",
      {
        projectName,
        functionName: "discovery-completion",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "jobs",
          "discovery_completion",
        ),
        timeout: 180,
        memorySize: 1024,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
        },
      },
    );

    const discoveryFailureFinalizer = new DockerFunction(
      this,
      "DiscoveryFailureFinalizerConstruct",
      {
        projectName,
        functionName: "discovery-failure-finalizer",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "jobs",
          "discovery_failure_finalizer",
        ),
        timeout: 60,
        memorySize: 512,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
        },
      },
    );

    const discoverySpotHistoryProcessor = new DockerFunction(
      this,
      "DiscoverySpotHistoryProcessorConstruct",
      {
        projectName,
        functionName: "discovery-spot-history-processor",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "jobs",
          "discovery_spot_history_processor",
        ),
        timeout: 180,
        memorySize: 1024,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
        },
      },
    );

    const discoveryCatalogBuilder = new DockerFunction(
      this,
      "DiscoveryCatalogBuilderConstruct",
      {
        projectName,
        functionName: "discovery-catalog-builder",
        codePath: path.join(
          codebuildSrcDir,
          "..",
          "packages",
          "jobs",
          "discovery_catalog_builder",
        ),
        timeout: 180,
        memorySize: 1024,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
        },
      },
    );

    dataBucket.grantReadWrite(sitemapScraper.lambdaFunction);
    dataBucket.grantReadWrite(spotScraper.lambdaFunction);
    dataBucket.grantReadWrite(discoveryDiff.lambdaFunction);
    dataBucket.grantReadWrite(discoveryCompletion.lambdaFunction);
    dataBucket.grantReadWrite(discoveryFailureFinalizer.lambdaFunction);
    dataBucket.grantReadWrite(discoverySpotHistoryProcessor.lambdaFunction);
    dataBucket.grantReadWrite(discoveryCatalogBuilder.lambdaFunction);
    spotScraper.queue.grantSendMessages(discoveryDiff.lambdaFunction);
    spotScraper.deadLetterQueue.grantConsumeMessages(
      discoveryFailureFinalizer.lambdaFunction,
    );
    discoveryFailureFinalizer.lambdaFunction.addEventSource(
      new lambdaEventSources.SqsEventSource(spotScraper.deadLetterQueue, {
        batchSize: 1,
        enabled: true,
        reportBatchItemFailures: true,
      }),
    );

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

    new events.Rule(this, "DiscoveryCompletionRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: {
            key: [
              { prefix: "control/completions/discovery_spot_scrapes/" },
              { prefix: "control/completions/discovery_spot_scrapes_failed/" },
            ],
          },
        },
      },
      targets: [new targets.LambdaFunction(discoveryCompletion.lambdaFunction)],
    });

    new events.Rule(this, "DiscoverySpotHistoryProcessorRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: {
            key: [
              {
                prefix:
                  "control/manifests/processing/domain=discovery/stage=spot_history/",
              },
            ],
          },
        },
      },
      targets: [
        new targets.LambdaFunction(
          discoverySpotHistoryProcessor.lambdaFunction,
        ),
      ],
    });

    new events.Rule(this, "DiscoveryCatalogBuilderRule", {
      eventPattern: {
        source: ["aws.s3"],
        detailType: ["Object Created"],
        detail: {
          bucket: { name: [dataBucket.bucketName] },
          object: {
            key: [
              {
                prefix:
                  "control/manifests/processing/domain=discovery/stage=catalog_build/",
              },
            ],
          },
        },
      },
      targets: [
        new targets.LambdaFunction(discoveryCatalogBuilder.lambdaFunction),
      ],
    });
  }
}
