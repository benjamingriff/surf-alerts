from aws_lambda_powertools import Logger

logger = Logger(service="spot-scraper")

inject_lambda_context = logger.inject_lambda_context


def get_logger() -> Logger:
    return logger
