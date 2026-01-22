import { Construct } from "constructs";
import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as ecrAssets from "aws-cdk-lib/aws-ecr-assets";
import * as s3 from "aws-cdk-lib/aws-s3";

export interface ScheduledScraperProps {
  projectName: string;
  scraperName: string;
  codePath: string;
  timeout: number;
  memorySize: number;
  schedule: events.Schedule;
  bucket: s3.IBucket;
}

export class ScheduledScraper extends Construct {
  public readonly lambdaFunction: lambda.Function;
  public readonly rule: events.Rule;

  constructor(scope: Construct, id: string, props: ScheduledScraperProps) {
    super(scope, id);

    const imageAsset = new ecrAssets.DockerImageAsset(
      this,
      "ScraperDockerImage",
      {
        directory: props.codePath,
      },
    );

    this.lambdaFunction = new lambda.DockerImageFunction(
      this,
      "ScraperLambdaFn",
      {
        code: lambda.DockerImageCode.fromEcr(imageAsset.repository, {
          tagOrDigest: imageAsset.imageTag,
        }),
        memorySize: props.memorySize,
        timeout: cdk.Duration.seconds(props.timeout),
        functionName: `${props.projectName}-${props.scraperName}`,
        environment: {
          POWERTOOLS_LOG_LEVEL: "INFO",
          BUCKET_NAME: props.bucket.bucketName,
        },
      },
    );

    // Grant the Lambda function read/write access to the S3 bucket
    props.bucket.grantReadWrite(this.lambdaFunction);

    // Create EventBridge rule to trigger the Lambda on schedule
    this.rule = new events.Rule(this, "ScheduleRule", {
      ruleName: `${props.projectName}-${props.scraperName}-schedule`,
      schedule: props.schedule,
    });

    this.rule.addTarget(new targets.LambdaFunction(this.lambdaFunction));
  }
}
