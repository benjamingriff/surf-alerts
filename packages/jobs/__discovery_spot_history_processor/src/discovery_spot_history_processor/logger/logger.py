from aws_lambda_powertools import Logger

logger = Logger(service="discovery-spot-history-processor")

inject_lambda_context = logger.inject_lambda_context


def get_logger() -> Logger:
    return logger
