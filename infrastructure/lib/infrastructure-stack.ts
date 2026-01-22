import * as cdk from "aws-cdk-lib";
import * as path from "path";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as events from "aws-cdk-lib/aws-events";
import { Construct } from "constructs";
import { ScheduledScraper } from "./constructs/scheduled-scraper";

export class InfrastructureStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const codebuildSrcDir = process.env.CODEBUILD_SRC_DIR ?? ".";

    // S3 bucket for storing scraped data
    const dataBucket = new s3.Bucket(this, "DataBucket", {
      bucketName: `${this.stackName.toLowerCase()}-data`,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });

    // Sitemap scraper - runs daily at 06:00 UTC
    new ScheduledScraper(this, "SitemapScraperConstruct", {
      projectName: this.stackName,
      scraperName: "sitemap-scraper",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "scrapers",
        "sitemap_scraper",
      ),
      timeout: 60,
      memorySize: 1024,
      schedule: events.Schedule.cron({ hour: "6", minute: "0" }),
      bucket: dataBucket,
    });

    // Taxonomy scraper - runs daily at 06:00 UTC (parallel with sitemap)
    // Longer timeout for recursive API calls
    new ScheduledScraper(this, "TaxonomyScraperConstruct", {
      projectName: this.stackName,
      scraperName: "taxonomy-scraper",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "scrapers",
        "taxonomy_scraper",
      ),
      timeout: 600, // 10 minutes for recursive scraping
      memorySize: 1024,
      schedule: events.Schedule.cron({ hour: "6", minute: "0" }),
      bucket: dataBucket,
    });

    // Spot reconciler - runs daily at 06:15 UTC (after scrapers complete)
    new ScheduledScraper(this, "SpotReconcilerConstruct", {
      projectName: this.stackName,
      scraperName: "spot-reconciler",
      codePath: path.join(
        codebuildSrcDir,
        "..",
        "packages",
        "jobs",
        "spot_reconciler",
      ),
      timeout: 120,
      memorySize: 1024,
      schedule: events.Schedule.cron({ hour: "6", minute: "15" }),
      bucket: dataBucket,
    });
  }
}
