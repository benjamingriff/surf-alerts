import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { InfrastructureStack } from "../lib/infrastructure-stack";

test("discovery infrastructure resources are synthesized", () => {
  const app = new cdk.App();
  const stack = new InfrastructureStack(app, "SufAlertsStack");
  const template = Template.fromStack(stack);

  template.resourceCountIs("AWS::Events::Rule", 5);

  [
    "surf-alerts-sitemap-scraper",
    "surf-alerts-spot-scraper",
    "surf-alerts-discovery-diff",
    "surf-alerts-discovery-completion",
    "surf-alerts-discovery-failure-finalizer",
    "surf-alerts-discovery-spot-history-processor",
    "surf-alerts-discovery-catalog-builder",
  ].forEach((functionName) => {
    template.hasResourceProperties("AWS::Lambda::Function", {
      FunctionName: functionName,
    });
  });

  template.hasResourceProperties("AWS::SQS::Queue", {
    QueueName: "surf-alerts-spot-scraper-queue",
  });

  template.hasResourceProperties("AWS::Events::Rule", {
    EventPattern: {
      source: ["aws.s3"],
      "detail-type": ["Object Created"],
      detail: {
        object: {
          key: Match.arrayWith([Match.objectLike({ prefix: "raw/sitemap/" })]),
        },
      },
    },
  });

  template.hasResourceProperties("AWS::Lambda::EventSourceMapping", {
    BatchSize: 1,
    EventSourceArn: {
      "Fn::GetAtt": [Match.stringLikeRegexp("SpotScraperConstructScraperQueueQueueDLQ"), "Arn"],
    },
    FunctionName: {
      Ref: Match.stringLikeRegexp("DiscoveryFailureFinalizerConstructLambdaFn"),
    },
  });
});
