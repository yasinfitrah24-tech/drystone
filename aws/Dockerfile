# Drystone decision service for AWS Lambda (container image: OpenCV 5 + MuJoCo are too big for a zip).
# Build from the repo root:  docker build -f aws/Dockerfile -t drystone-service .
FROM public.ecr.aws/lambda/python:3.12
COPY aws/requirements-lambda.txt .
RUN pip install --no-cache-dir -r requirements-lambda.txt
COPY tools/ ${LAMBDA_TASK_ROOT}/
COPY config/boxes.json ${LAMBDA_TASK_ROOT}/config/boxes.json
COPY data/camera_laptop.yaml ${LAMBDA_TASK_ROOT}/data/camera_laptop.yaml
ENV DRYSTONE_CALIB=${LAMBDA_TASK_ROOT}/data/camera_laptop.yaml \
    DRYSTONE_BOXES=${LAMBDA_TASK_ROOT}/config/boxes.json \
    DRYSTONE_MARKER_MM=80 \
    MPLCONFIGDIR=/tmp
CMD ["service.lambda_handler"]
