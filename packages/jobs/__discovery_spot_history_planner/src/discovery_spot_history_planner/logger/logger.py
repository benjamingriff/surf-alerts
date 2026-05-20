from aws_lambda_powertools import Logger

logger = Logger(service="discovery-spot-history-planner")
inject_lambda_context = logger.inject_lambda_context


def get_logger():
    return logger
