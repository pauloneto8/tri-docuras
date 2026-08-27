FROM dart:3.7.2

WORKDIR /app

RUN dart pub global activate dart_frog_cli
ENV PATH="/root/.pub-cache/bin:${PATH}"

COPY pubspec.yaml pubspec.lock* ./
RUN dart pub get

COPY . .
RUN dart_frog build
RUN chmod +x entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
