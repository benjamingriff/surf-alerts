import { Construct } from "constructs";
import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import * as ecrAssets from "aws-cdk-lib/aws-ecr-assets";
import { SqsQueue } from "./sqs-queue";

export interface ScraperWorkerProps {
  projectName: string;
  scraperName: string;
  codePath: string;
  timeout: number;
  memorySize: number;
  maxConcurrency?: number;
}

export class ScraperWorker extends Construct {
  public readonly lambdaFunction: lambda.Function;
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;

  constructor(scope: Construct, id: string, props: ScraperWorkerProps) {
    super(scope, id);

    const sqsConstruct = new SqsQueue(this, "ScraperQueue", {
      queueName: `${props.projectName}-${props.scraperName}-queue`,
      visibilityTimeout: cdk.Duration.seconds(props.timeout * 3),
    });

    this.queue = sqsConstruct.queue;
    this.deadLetterQueue = sqsConstruct.deadLetterQueue;

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
        },
      },
    );

    this.queue.grantConsumeMessages(this.lambdaFunction);

    this.lambdaFunction.addEventSource(
      new lambdaEventSources.SqsEventSource(this.queue, {
        batchSize: 1,
        maxConcurrency: props.maxConcurrency ?? 2,
        enabled: true,
        reportBatchItemFailures: true,
      }),
    );
  }
}
