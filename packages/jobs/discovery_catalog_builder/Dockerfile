FROM ghcr.io/astral-sh/uv:0.9.4 AS uv

FROM public.ecr.aws/lambda/python:3.12 AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1
ENV UV_LINK_MODE=copy

RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --no-emit-workspace --no-dev --no-editable -o requirements.txt && \
    uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

FROM public.ecr.aws/lambda/python:3.12

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}
COPY ./src ${LAMBDA_TASK_ROOT}/src

ENV PYTHONPATH="${LAMBDA_TASK_ROOT}:${LAMBDA_TASK_ROOT}/src:${PYTHONPATH}"

CMD ["discovery_catalog_builder.handler.lambda_handler"]
