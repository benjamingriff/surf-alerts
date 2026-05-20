FROM ghcr.io/astral-sh/uv:0.9.4 AS uv
FROM public.ecr.aws/lambda/python:3.12 AS builder

ENV UV_COMPILE_BYTECODE=1 UV_NO_INSTALLER_METADATA=1 UV_LINK_MODE=copy
WORKDIR /build

COPY pyproject.toml uv.lock ./
COPY packages/jobs/discovery_spot_batch_processor packages/jobs/discovery_spot_batch_processor
COPY packages/libs/postgres_client packages/libs/postgres_client
COPY packages/libs/discovery_control packages/libs/discovery_control
COPY packages/libs/discovery_spot_model packages/libs/discovery_spot_model

RUN --mount=from=uv,source=/uv,target=/bin/uv \
   --mount=type=cache,target=/root/.cache/uv \
   uv export --package discovery-spot-batch-processor --no-dev --no-editable -o requirements.txt \
   && uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

FROM public.ecr.aws/lambda/python:3.12

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

ENV PYTHONPATH="${LAMBDA_TASK_ROOT}"

CMD ["discovery_spot_batch_processor.handler.lambda_handler"]
