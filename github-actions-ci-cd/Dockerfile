FROM eclipse-temurin:25
WORKDIR /app
# Copy the built JAR file into the container
COPY target/*.jar app.jar
# Expose the application port (if needed)
EXPOSE 8080
# Run the application
ENTRYPOINT ["java", "-jar", "app.jar"]