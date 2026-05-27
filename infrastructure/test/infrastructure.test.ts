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
    "surf-alerts-forecast-completion-queue",
  ].forEach((queueName) => template.hasResourceProperties("AWS::SQS::Queue", { QueueName: queueName }));

  template.hasResourceProperties("AWS::DynamoDB::Table", {
    TableName: "surf-alerts-discovery-control",
    TimeToLiveSpecification: { AttributeName: "expires_at", Enabled: true },
  });

  template.resourceCountIs("AWS::Events::Rule", 2);
  template.hasResourceProperties("AWS::Events::Rule", {
    ScheduleExpression: "cron(0 6 1 * ? *)",
  });

  template.hasResourceProperties("AWS::S3::Bucket", {
    LifecycleConfiguration: {
      Rules: Match.arrayWith([
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
    FunctionName: "surf-alerts-forecast-spot-processor",
    Timeout: 300,
    MemorySize: 1024,
  });
  template.hasResourceProperties("AWS::SQS::Queue", {
    QueueName: "surf-alerts-forecast-completion-queue",
    VisibilityTimeout: 1800,
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
