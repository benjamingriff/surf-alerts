import * as cdk from "aws-cdk-lib";
import * as path from "path";
import { Construct } from "constructs";
import { ScraperWorker } from "./constructs/scraper";

export class InfrastructureStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const codebuildSrcDir = process.env.CODEBUILD_SRC_DIR ?? ".";

    new ScraperWorker(this, "GooglePagesScraperConstruct", {
      projectName: this.stackName,
      scraperName: "spot-scraper",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "scrapers",
        "spot_scraper",
      ),
      timeout: 60,
      memorySize: 1024,
    });
  }
}
