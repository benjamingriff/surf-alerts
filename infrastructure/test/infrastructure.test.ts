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
  ].forEach((functionName) => {
    template.hasResourceProperties("AWS::Lambda::Function", { FunctionName: functionName });
  });

  [
    "surf-alerts-spot-scraper-queue",
    "surf-alerts-discovery-completion-queue",
    "surf-alerts-discovery-run-planner-queue",
    "surf-alerts-discovery-spot-batch-processor-queue",
  ].forEach((queueName) => template.hasResourceProperties("AWS::SQS::Queue", { QueueName: queueName }));

  template.hasResourceProperties("AWS::DynamoDB::Table", {
    TableName: "surf-alerts-discovery-control",
    TimeToLiveSpecification: { AttributeName: "expires_at", Enabled: true },
  });

  template.resourceCountIs("AWS::Events::Rule", 1);
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
});
