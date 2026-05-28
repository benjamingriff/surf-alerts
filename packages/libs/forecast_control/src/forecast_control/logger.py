from aws_lambda_powertools import Logger

logger = Logger(service="forecast-control")
logger.setLevel("INFO")


def get_logger() -> Logger:
    return logger
