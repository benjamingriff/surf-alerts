from aws_lambda_powertools import Logger

logger = Logger(service="forecast-control")


def get_logger() -> Logger:
    return logger
