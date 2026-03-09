import * as cdk from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { InfrastructureStack } from "../lib/infrastructure-stack";

test("discovery infrastructure resources are synthesized", () => {
  const app = new cdk.App();
  const stack = new InfrastructureStack(app, "SufAlertsStack");
  const template = Template.fromStack(stack);

  template.resourceCountIs("AWS::Events::Rule", 5);

  [
    "SufAlertsStack-sitemap-scraper",
    "SufAlertsStack-spot-scraper",
    "SufAlertsStack-discovery-diff",
    "SufAlertsStack-spot-report-processor",
    "SufAlertsStack-discovery-completion",
    "SufAlertsStack-catalog-builder",
  ].forEach((functionName) => {
    template.hasResourceProperties("AWS::Lambda::Function", {
      FunctionName: functionName,
    });
  });

  template.hasResourceProperties("AWS::SQS::Queue", {
    QueueName: "SufAlertsStack-spot-scraper-queue",
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
});
