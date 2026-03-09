from aws_lambda_powertools import Logger

logger = Logger(service="spot-report-processor")

inject_lambda_context = logger.inject_lambda_context


def get_logger() -> Logger:
    return logger
