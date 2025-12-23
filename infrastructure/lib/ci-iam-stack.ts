import { Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";

export interface CiIamStackProps extends StackProps {
  readonly githubOwner: string; // username (personal) OR org
  readonly githubRepo: string;
  readonly githubBranch?: string;
  readonly cdkQualifier?: string;
}

export class CiIamStack extends Stack {
  constructor(scope: Construct, id: string, props: CiIamStackProps) {
    super(scope, id, props);

    const githubBranch = props.githubBranch ?? "main";
    const cdkQualifier = props.cdkQualifier ?? "hnb659fds";

    const provider = new iam.OpenIdConnectProvider(this, "GitHubOidcProvider", {
      url: "https://token.actions.githubusercontent.com",
      clientIds: ["sts.amazonaws.com"],
    });

    const sub = `repo:${props.githubOwner}/${props.githubRepo}:ref:refs/heads/${githubBranch}`;

    const deployRole = new iam.Role(this, "GitHubActionsCdkDeployRole", {
      roleName: "GitHubActionsCdkDeployRole",
      assumedBy: new iam.WebIdentityPrincipal(
        provider.openIdConnectProviderArn,
        {
          StringEquals: {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": sub,
          },
        },
      ),
    });

    deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["sts:AssumeRole"],
        resources: [`arn:aws:iam::${this.account}:role/cdk-${cdkQualifier}-*`],
      }),
    );
  }
}
