import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as sqs from "aws-cdk-lib/aws-sqs";

export interface SqsQueueProps {
  queueName: string;
  visibilityTimeout: cdk.Duration;
}

export class SqsQueue extends Construct {
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;

  constructor(scope: Construct, id: string, props: SqsQueueProps) {
    super(scope, id);

    this.deadLetterQueue = new sqs.Queue(this, "QueueDLQ", {
      queueName: `${props.queueName}-dlq`,
      retentionPeriod: cdk.Duration.days(7),
    });

    this.queue = new sqs.Queue(this, "Queue", {
      queueName: props.queueName,
      visibilityTimeout: props.visibilityTimeout,
      retentionPeriod: cdk.Duration.days(1),
      deadLetterQueue: {
        queue: this.deadLetterQueue,
        maxReceiveCount: 3,
      },
    });
  }
}
