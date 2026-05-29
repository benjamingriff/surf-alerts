import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { InfrastructureStack } from "../lib/infrastructure-stack";

test("discovery infrastructure resources are synthesized", () => {
  const app = new cdk.App();
  const stack = new InfrastructureStack(app, "SufAlertsStack");
  const template = Template.fromStack(stack);

  [
    "surf-alerts-sitemap-scraper",
    "surf-alerts-spot-scraper",
    "surf-alerts-discovery-run-planner",
    "surf-alerts-discovery-completion",
    "surf-alerts-discovery-spot-batch-processor",
    "surf-alerts-forecast-scraper",
    "surf-alerts-forecast-run-planner",
    "surf-alerts-forecast-spot-processor",
  ].forEach((functionName) => {
    template.hasResourceProperties("AWS::Lambda::Function", { FunctionName: functionName });
  });

  [
    "surf-alerts-spot-scraper-queue",
    "surf-alerts-discovery-completion-queue",
    "surf-alerts-discovery-run-planner-queue",
    "surf-alerts-discovery-spot-batch-processor-queue",
    "surf-alerts-forecast-scraper-queue",
    "surf-alerts-forecast-completion-queue",
  ].forEach((queueName) => template.hasResourceProperties("AWS::SQS::Queue", { QueueName: queueName }));

  template.hasResourceProperties("AWS::DynamoDB::Table", {
    TableName: "surf-alerts-discovery-control",
    KeySchema: Match.arrayWith([
      { AttributeName: "pk", KeyType: "HASH" },
      { AttributeName: "sk", KeyType: "RANGE" },
    ]),
    TimeToLiveSpecification: { AttributeName: "expires_at", Enabled: true },
  });
  template.hasResourceProperties("AWS::DynamoDB::Table", {
    TableName: "surf-alerts-forecast-control",
    KeySchema: Match.arrayWith([
      { AttributeName: "pk", KeyType: "HASH" },
      { AttributeName: "sk", KeyType: "RANGE" },
    ]),
    TimeToLiveSpecification: { AttributeName: "expires_at", Enabled: true },
  });

  template.resourceCountIs("AWS::Events::Rule", 2);
  template.hasResourceProperties("AWS::Events::Rule", {
    ScheduleExpression: "cron(0 6 1 * ? *)",
  });
  template.hasResourceProperties("AWS::Events::Rule", {
    ScheduleExpression: "cron(0 * * * ? *)",
    Targets: Match.arrayWith([
      Match.objectLike({ Arn: { "Fn::GetAtt": [Match.stringLikeRegexp("ForecastRunPlannerConstructLambdaFn"), "Arn"] } }),
    ]),
  });

  template.hasResourceProperties("AWS::S3::Bucket", {
    LifecycleConfiguration: {
      Rules: Match.arrayWith([
        Match.objectLike({ Prefix: "raw/forecast/", Status: "Enabled", ExpirationInDays: 90 }),
        Match.objectLike({ Prefix: "raw/", Status: "Enabled" }),
        Match.objectLike({ Prefix: "control/", Status: "Enabled" }),
      ]),
    },
  });

  template.hasResourceProperties("AWS::Lambda::EventSourceMapping", {
    BatchSize: 10,
    FunctionName: { Ref: Match.stringLikeRegexp("DiscoveryCompletionConstructLambdaFn") },
  });

  template.hasResourceProperties("AWS::Lambda::Function", {
    FunctionName: "surf-alerts-forecast-scraper",
    Timeout: 60,
    MemorySize: 1024,
    Environment: {
      Variables: Match.objectLike({
        DATA_BUCKET: { Ref: Match.stringLikeRegexp("DataBucket") },
        FORECAST_COMPLETION_QUEUE_URL: { Ref: Match.stringLikeRegexp("ForecastCompletionQueue") },
      }),
    },
  });
  template.hasResourceProperties("AWS::Lambda::Function", {
    FunctionName: "surf-alerts-forecast-run-planner",
    Timeout: 300,
    MemorySize: 1024,
    Environment: {
      Variables: Match.objectLike({
        FORECAST_CONTROL_TABLE_NAME: { Ref: Match.stringLikeRegexp("ForecastControlTable") },
        FORECAST_SCRAPER_QUEUE_URL: { Ref: Match.stringLikeRegexp("ForecastScraperConstructScraperQueue") },
        FORECAST_SCRAPE_LOCAL_TIME: "04:00",
        FORECAST_MIN_UTC_OFFSET: "-12",
        FORECAST_MAX_UTC_OFFSET: "14",
        POSTGRES_URL_PARAMETER_NAME: "/surf-alerts/rds/postgres-url",
      }),
    },
  });
  template.hasResourceProperties("AWS::Lambda::Function", {
    FunctionName: "surf-alerts-forecast-spot-processor",
    Timeout: 300,
    MemorySize: 1024,
    Environment: {
      Variables: Match.objectLike({
        FORECAST_CONTROL_TABLE_NAME: { Ref: Match.stringLikeRegexp("ForecastControlTable") },
        POSTGRES_URL_PARAMETER_NAME: "/surf-alerts/rds/postgres-url",
      }),
    },
  });
  template.hasResourceProperties("AWS::SQS::Queue", {
    QueueName: "surf-alerts-forecast-scraper-queue",
    VisibilityTimeout: 360,
    RedrivePolicy: {
      deadLetterTargetArn: { "Fn::GetAtt": [Match.stringLikeRegexp("ForecastScraperConstructScraperQueueQueueDLQ"), "Arn"] },
      maxReceiveCount: 3,
    },
  });
  template.hasResourceProperties("AWS::SQS::Queue", {
    QueueName: "surf-alerts-forecast-completion-queue",
    VisibilityTimeout: 1800,
    RedrivePolicy: {
      deadLetterTargetArn: { "Fn::GetAtt": [Match.stringLikeRegexp("ForecastCompletionQueueQueueDLQ"), "Arn"] },
      maxReceiveCount: 3,
    },
  });
  template.hasResourceProperties("AWS::Lambda::EventSourceMapping", {
    BatchSize: 1,
    ScalingConfig: { MaximumConcurrency: 2 },
    FunctionName: { Ref: Match.stringLikeRegexp("ForecastScraperConstructScraperLambdaFn") },
  });
  template.hasResourceProperties("AWS::Lambda::EventSourceMapping", {
    BatchSize: 1,
    ScalingConfig: { MaximumConcurrency: 2 },
    FunctionName: { Ref: Match.stringLikeRegexp("ForecastSpotProcessorConstructLambdaFn") },
  });
  template.hasResourceProperties("AWS::IAM::Policy", {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Action: "dynamodb:TransactWriteItems",
          Effect: "Allow",
          Resource: {
            "Fn::GetAtt": [
              Match.stringLikeRegexp("ForecastControlTable"),
              "Arn",
            ],
          },
        }),
      ]),
    },
  });
});
