# Docker Setup for Potato & Onion Commodity Intelligence

This guide explains how to run the application using Docker.

## Prerequisites

- Docker installed on your system
- Docker Compose (optional, for easier management)

## Quick Start

### Option 1: Using Docker directly

1. **Build the image:**
   ```bash
   docker build -t potato-onion-intelligence .
   ```

2. **Run the container:**
   ```bash
   docker run -p 8501:8501 --name potato-onion-app potato-onion-intelligence
   ```

3. **Access the application:**
   Open your browser and go to `http://localhost:8501`

### Option 2: Using Docker Compose (Recommended)

1. **Start the application:**
   ```bash
   docker-compose up -d
   ```

2. **View logs:**
   ```bash
   docker-compose logs -f
   ```

3. **Stop the application:**
   ```bash
   docker-compose down
   ```

### Option 3: Using the provided script

1. **Make the script executable (if not already):**
   ```bash
   chmod +x docker-run.sh
   ```

2. **Run the script:**
   ```bash
   ./docker-run.sh
   ```

## Container Management

### View running containers
```bash
docker ps
```

### Stop the container
```bash
docker stop potato-onion-app
```

### Remove the container
```bash
docker rm potato-onion-app
```

### View application logs
```bash
docker logs potato-onion-app
```

### Access container shell
```bash
docker exec -it potato-onion-app /bin/bash
```

## Configuration

The application uses the following configuration files:
- `config.json` - Main application configuration
- `.streamlit/config.toml` - Streamlit configuration
- `.streamlit/credentials.toml` - Streamlit credentials

These files are copied into the Docker image during build. To modify them:

1. Update the files locally
2. Rebuild the Docker image
3. Restart the container

## Port Configuration

The application runs on port 8501 inside the container and is mapped to port 8501 on your host machine. To use a different port:

```bash
docker run -p 9000:8501 --name potato-onion-app potato-onion-intelligence
```

Then access the application at `http://localhost:9000`

## Environment Variables

You can set environment variables when running the container:

```bash
docker run -p 8501:8501 -e PYTHONUNBUFFERED=1 --name potato-onion-app potato-onion-intelligence
```

## Troubleshooting

### Container won't start
- Check Docker logs: `docker logs potato-onion-app`
- Ensure port 8501 is not already in use
- Verify all required files are present

### Application not accessible
- Check if the container is running: `docker ps`
- Verify port mapping: `docker port potato-onion-app`
- Check firewall settings

### Build issues
- Ensure all files are present in the build context
- Check Docker daemon is running
- Verify internet connection for downloading dependencies

## Development

For development with live code reloading, you can mount your local code:

```bash
docker run -p 8501:8501 -v $(pwd):/app --name potato-onion-dev potato-onion-intelligence
```

Note: You may need to install dependencies locally or rebuild the image when requirements change.