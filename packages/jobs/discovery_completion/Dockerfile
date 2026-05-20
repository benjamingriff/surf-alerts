FROM ghcr.io/astral-sh/uv:0.9.4 AS uv
FROM public.ecr.aws/lambda/python:3.12 AS builder

ENV UV_COMPILE_BYTECODE=1 UV_NO_INSTALLER_METADATA=1 UV_LINK_MODE=copy
WORKDIR /build

COPY pyproject.toml uv.lock ./
COPY packages/jobs/discovery_completion packages/jobs/discovery_completion
COPY packages/libs/discovery_control packages/libs/discovery_control

RUN --mount=from=uv,source=/uv,target=/bin/uv \
   --mount=type=cache,target=/root/.cache/uv \
   mkdir /wheels \
   && uv build --package discovery-control --wheel --out-dir /wheels \
   && uv build --package discovery-completion --wheel --out-dir /wheels \
   && uv pip install --find-links /wheels discovery-completion==0.1.0 --target "${LAMBDA_TASK_ROOT}"

FROM public.ecr.aws/lambda/python:3.12

COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

ENV PYTHONPATH="${LAMBDA_TASK_ROOT}"

CMD ["discovery_completion.handler.lambda_handler"]
