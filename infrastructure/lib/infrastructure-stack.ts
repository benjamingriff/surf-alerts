import * as cdk from "aws-cdk-lib";
import * as path from "path";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import { DockerFunction } from "./constructs/docker-function";
import { ScheduledScraper } from "./constructs/scheduled-scraper";
import { ScraperWorker } from "./constructs/scraper";
import { SqsQueue } from "./constructs/sqs-queue";

export class InfrastructureStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const projectName = "surf-alerts";
    const codebuildSrcDir =
      process.env.CODEBUILD_SRC_DIR ?? path.join(__dirname, "..", "..");

    const dataBucket = new s3.Bucket(this, "DataBucket", {
      bucketName: `${projectName}-data`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      encryption: s3.BucketEncryption.S3_MANAGED,
      eventBridgeEnabled: false,
      lifecycleRules: [
        {
          prefix: "raw/",
          expiration: cdk.Duration.days(120),
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
        },
        {
          prefix: "control/",
          expiration: cdk.Duration.days(14),
          abortIncompleteMultipartUploadAfter: cdk.Duration.days(7),
        },
      ],
    });

    const discoveryControlTable = new dynamodb.Table(
      this,
      "DiscoveryControlTable",
      {
        tableName: `${projectName}-discovery-control`,
        partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
        sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        timeToLiveAttribute: "expires_at",
        removalPolicy: cdk.RemovalPolicy.RETAIN,
      },
    );

    const forecastControlTable = new dynamodb.Table(
      this,
      "ForecastControlTable",
      {
        tableName: `${projectName}-forecast-control`,
        partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
        sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        timeToLiveAttribute: "expires_at",
        removalPolicy: cdk.RemovalPolicy.RETAIN,
      },
    );

    const discoveryCompletionQueue = new SqsQueue(
      this,
      "DiscoveryCompletionQueue",
      {
        queueName: `${projectName}-discovery-completion-queue`,
        visibilityTimeout: cdk.Duration.seconds(180 * 6),
      },
    );

    const discoveryRunPlannerQueue = new SqsQueue(
      this,
      "DiscoveryRunPlannerQueue",
      {
        queueName: `${projectName}-discovery-run-planner-queue`,
        visibilityTimeout: cdk.Duration.seconds(300 * 6),
      },
    );

    const discoverySpotBatchProcessorQueue = new SqsQueue(
      this,
      "DiscoverySpotBatchProcessorQueue",
      {
        queueName: `${projectName}-discovery-spot-batch-processor-queue`,
        visibilityTimeout: cdk.Duration.seconds(900 * 6),
      },
    );

    const forecastCompletionQueue = new SqsQueue(this, "ForecastCompletionQueue", {
      queueName: `${projectName}-forecast-completion-queue`,
      visibilityTimeout: cdk.Duration.seconds(1800),
    });

    const supabasePostgresUrl =
      ssm.StringParameter.fromSecureStringParameterAttributes(
        this,
        "SupabasePostgresUrlParameter",
        { parameterName: "/surf-alerts/supabase/postgres-url" },
      );

    const sitemapScraper = new ScheduledScraper(
      this,
      "SitemapScraperConstruct",
      {
        projectName,
        scraperName: "sitemap-scraper",
        codePath: path.join(
          codebuildSrcDir,
          "packages",
          "scrapers",
          "sitemap_scraper",
        ),
        timeout: 60,
        memorySize: 1024,
        schedule: events.Schedule.cron({
          day: "1",
          hour: "6",
          minute: "0",
        }),
        bucket: dataBucket,
        environment: {
          DISCOVERY_RUN_PLANNER_QUEUE_URL:
            discoveryRunPlannerQueue.queue.queueUrl,
        },
      },
    );

    const spotScraper = new ScraperWorker(this, "SpotScraperConstruct", {
      projectName,
      scraperName: "spot-scraper",
      codePath: path.join(
        codebuildSrcDir,
        "packages",
        "scrapers",
        "spot_scraper",
      ),
      timeout: 60,
      memorySize: 1024,
      environment: {
        DATA_BUCKET: dataBucket.bucketName,
        DISCOVERY_COMPLETION_QUEUE_URL: discoveryCompletionQueue.queue.queueUrl,
      },
    });

    const forecastScraper = new ScraperWorker(this, "ForecastScraperConstruct", {
      projectName,
      scraperName: "forecast-scraper",
      codePath: path.join(
        codebuildSrcDir,
        "packages",
        "scrapers",
        "forecast_scraper",
      ),
      timeout: 60,
      memorySize: 1024,
      environment: {
        DATA_BUCKET: dataBucket.bucketName,
        FORECAST_COMPLETION_QUEUE_URL: forecastCompletionQueue.queue.queueUrl,
      },
    });

    const discoveryRunPlanner = new DockerFunction(
      this,
      "DiscoveryRunPlannerConstruct",
      {
        projectName,
        functionName: "discovery-run-planner",
        codePath: codebuildSrcDir,
        dockerfile: path.join(
          "packages",
          "jobs",
          "discovery_run_planner",
          "Dockerfile",
        ),
        timeout: 300,
        memorySize: 1024,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
          DISCOVERY_CONTROL_TABLE_NAME: discoveryControlTable.tableName,
          SPOT_SCRAPER_QUEUE_URL: spotScraper.queue.queueUrl,
          DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL:
            discoverySpotBatchProcessorQueue.queue.queueUrl,
          SUPABASE_POSTGRES_URL_PARAMETER_NAME:
            "/surf-alerts/supabase/postgres-url",
        },
      },
    );

    const forecastRunPlanner = new DockerFunction(
      this,
      "ForecastRunPlannerConstruct",
      {
        projectName,
        functionName: "forecast-run-planner",
        codePath: codebuildSrcDir,
        dockerfile: path.join(
          "packages",
          "jobs",
          "forecast_run_planner",
          "Dockerfile",
        ),
        timeout: 300,
        memorySize: 1024,
        environment: {
          FORECAST_CONTROL_TABLE_NAME: forecastControlTable.tableName,
          FORECAST_SCRAPER_QUEUE_URL: forecastScraper.queue.queueUrl,
          FORECAST_SCRAPE_LOCAL_TIME: "04:00",
          FORECAST_MIN_UTC_OFFSET: "-12",
          FORECAST_MAX_UTC_OFFSET: "14",
          SUPABASE_POSTGRES_URL_PARAMETER_NAME:
            "/surf-alerts/supabase/postgres-url",
        },
      },
    );

    const discoveryCompletion = new DockerFunction(
      this,
      "DiscoveryCompletionConstruct",
      {
        projectName,
        functionName: "discovery-completion",
        codePath: codebuildSrcDir,
        dockerfile: path.join(
          "packages",
          "jobs",
          "discovery_completion",
          "Dockerfile",
        ),
        timeout: 180,
        memorySize: 1024,
        environment: {
          DISCOVERY_CONTROL_TABLE_NAME: discoveryControlTable.tableName,
          DISCOVERY_SPOT_BATCH_PROCESSOR_QUEUE_URL:
            discoverySpotBatchProcessorQueue.queue.queueUrl,
        },
      },
    );

    const discoverySpotBatchProcessor = new DockerFunction(
      this,
      "DiscoverySpotBatchProcessorConstruct",
      {
        projectName,
        functionName: "discovery-spot-batch-processor",
        codePath: codebuildSrcDir,
        dockerfile: path.join(
          "packages",
          "jobs",
          "discovery_spot_batch_processor",
          "Dockerfile",
        ),
        timeout: 900,
        memorySize: 1024,
        environment: {
          DATA_BUCKET: dataBucket.bucketName,
          DISCOVERY_CONTROL_TABLE_NAME: discoveryControlTable.tableName,
          DISCOVERY_SPOT_BATCH_S3_READ_WORKERS: "16",
          SUPABASE_POSTGRES_URL_PARAMETER_NAME:
            "/surf-alerts/supabase/postgres-url",
        },
      },
    );

    dataBucket.grantReadWrite(sitemapScraper.lambdaFunction);
    dataBucket.grantReadWrite(spotScraper.lambdaFunction);
    dataBucket.grantReadWrite(forecastScraper.lambdaFunction);
    dataBucket.grantReadWrite(discoveryRunPlanner.lambdaFunction);
    dataBucket.grantReadWrite(discoverySpotBatchProcessor.lambdaFunction);
    discoveryControlTable.grantReadWriteData(
      discoveryRunPlanner.lambdaFunction,
    );
    discoveryControlTable.grantReadWriteData(
      discoveryCompletion.lambdaFunction,
    );
    discoveryControlTable.grantReadWriteData(
      discoverySpotBatchProcessor.lambdaFunction,
    );
    forecastControlTable.grantReadWriteData(forecastRunPlanner.lambdaFunction);
    discoveryRunPlannerQueue.queue.grantSendMessages(
      sitemapScraper.lambdaFunction,
    );
    spotScraper.queue.grantSendMessages(discoveryRunPlanner.lambdaFunction);
    discoveryCompletionQueue.queue.grantSendMessages(
      spotScraper.lambdaFunction,
    );
    discoverySpotBatchProcessorQueue.queue.grantSendMessages(
      discoveryRunPlanner.lambdaFunction,
    );
    discoverySpotBatchProcessorQueue.queue.grantSendMessages(
      discoveryCompletion.lambdaFunction,
    );
    forecastScraper.queue.grantSendMessages(forecastRunPlanner.lambdaFunction);
    forecastCompletionQueue.queue.grantSendMessages(forecastScraper.lambdaFunction);
    supabasePostgresUrl.grantRead(discoveryRunPlanner.lambdaFunction);
    supabasePostgresUrl.grantRead(discoverySpotBatchProcessor.lambdaFunction);
    supabasePostgresUrl.grantRead(forecastRunPlanner.lambdaFunction);

    new events.Rule(this, "ForecastRunPlannerHourlyRule", {
      schedule: events.Schedule.cron({ minute: "0" }),
      targets: [new targets.LambdaFunction(forecastRunPlanner.lambdaFunction)],
    });

    discoveryRunPlanner.lambdaFunction.addEventSource(
      new lambdaEventSources.SqsEventSource(discoveryRunPlannerQueue.queue, {
        batchSize: 1,
        enabled: true,
        reportBatchItemFailures: false,
        maxConcurrency: 2,
      }),
    );
    discoveryCompletion.lambdaFunction.addEventSource(
      new lambdaEventSources.SqsEventSource(discoveryCompletionQueue.queue, {
        batchSize: 10,
        enabled: true,
        reportBatchItemFailures: false,
        maxConcurrency: 20,
      }),
    );
    discoverySpotBatchProcessor.lambdaFunction.addEventSource(
      new lambdaEventSources.SqsEventSource(
        discoverySpotBatchProcessorQueue.queue,
        {
          batchSize: 1,
          enabled: true,
          reportBatchItemFailures: false,
          maxConcurrency: 2,
        },
      ),
    );
  }
}
