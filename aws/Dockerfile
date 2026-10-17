# Drystone decision service for AWS Lambda (container image: OpenCV 5 + MuJoCo are too big for a zip).
# Build from the repo root:  docker build -f aws/Dockerfile -t drystone-service .
FROM public.ecr.aws/lambda/python:3.12
COPY aws/requirements-lambda.txt .
# From China, PyPI can be very slow: build with
#   docker build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -f aws/Dockerfile -t drystone-service .
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r requirements-lambda.txt
COPY tools/ ${LAMBDA_TASK_ROOT}/
COPY config/boxes.json ${LAMBDA_TASK_ROOT}/config/boxes.json
COPY data/camera_laptop.yaml ${LAMBDA_TASK_ROOT}/data/camera_laptop.yaml
# Judges' web page + sample photos, served by the same function (GET /, GET /samples/<id>.jpg)
COPY web/ ${LAMBDA_TASK_ROOT}/web/
ENV DRYSTONE_CALIB=${LAMBDA_TASK_ROOT}/data/camera_laptop.yaml \
    DRYSTONE_BOXES=${LAMBDA_TASK_ROOT}/config/boxes.json \
    DRYSTONE_MARKER_MM=80 \
    DRYSTONE_WEB=${LAMBDA_TASK_ROOT}/web \
    MPLCONFIGDIR=/tmp
CMD ["service.lambda_handler"]
