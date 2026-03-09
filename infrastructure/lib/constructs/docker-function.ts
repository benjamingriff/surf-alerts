import * as cdk from "aws-cdk-lib";
import * as ecrAssets from "aws-cdk-lib/aws-ecr-assets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";

export interface DockerFunctionProps {
  projectName: string;
  functionName: string;
  codePath: string;
  timeout: number;
  memorySize: number;
  environment?: Record<string, string>;
}

export class DockerFunction extends Construct {
  public readonly lambdaFunction: lambda.DockerImageFunction;

  constructor(scope: Construct, id: string, props: DockerFunctionProps) {
    super(scope, id);

    const imageAsset = new ecrAssets.DockerImageAsset(this, "DockerImage", {
      directory: props.codePath,
    });

    this.lambdaFunction = new lambda.DockerImageFunction(this, "LambdaFn", {
      code: lambda.DockerImageCode.fromEcr(imageAsset.repository, {
        tagOrDigest: imageAsset.imageTag,
      }),
      memorySize: props.memorySize,
      timeout: cdk.Duration.seconds(props.timeout),
      functionName: `${props.projectName}-${props.functionName}`,
      environment: {
        POWERTOOLS_LOG_LEVEL: "WARNING",
        ...props.environment,
      },
    });
  }
}
