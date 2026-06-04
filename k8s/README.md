# Kubernetes Deployment for Raytracer Application

This directory contains Kubernetes manifests for deploying the raytracer application.

## Structure

- **namespace.yaml** - Creates the `raytracer` namespace
- **secrets.yaml** - Stores sensitive data (passwords, API keys)
- **configmap.yaml** - Non-sensitive configuration variables
- **pvc.yaml** - PersistentVolumeClaims for PostgreSQL and MinIO (using Cinder storage class)
- **postgres-deployment.yaml** - PostgreSQL database deployment with service
- **rabbitmq-deployment.yaml** - RabbitMQ message broker deployment with service
- **minio-deployment.yaml** - MinIO object storage deployment with services
- **web-deployment.yaml** - Web application deployment with services
- **worker-deployment.yaml** - Worker deployment for rendering jobs
- **kustomization.yaml** - Kustomize configuration for easy deployment

## Deployment Instructions

### Prerequisites

1. Kubernetes cluster running (with Cinder storage class available)
2. kubectl configured to access your cluster
3. Docker images built and available:
   - `raytracer-webapp:latest`
   - `raytracer-worker:latest`

### Build Docker Images

Build the web application image:
```bash
docker build -t raytracer-webapp:latest ./webapp
```

Build the worker image:
```bash
docker build -t raytracer-worker:latest ./worker
```

Push to your container registry:
```bash
docker tag raytracer-webapp:latest <your-registry>/raytracer-webapp:latest
docker tag raytracer-worker:latest <your-registry>/raytracer-worker:latest
docker push <your-registry>/raytracer-webapp:latest
docker push <your-registry>/raytracer-worker:latest
```

Then update the image references in the deployment files.

### Deploy with Kustomize

```bash
kubectl apply -k .
```

Or deploy individual files:

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create secrets and config
kubectl apply -f secrets.yaml
kubectl apply -f configmap.yaml

# Create persistent volumes
kubectl apply -f pvc.yaml

# Deploy services
kubectl apply -f postgres-deployment.yaml
kubectl apply -f rabbitmq-deployment.yaml
kubectl apply -f minio-deployment.yaml
kubectl apply -f web-deployment.yaml
kubectl apply -f worker-deployment.yaml
```

### Verify Deployment

```bash
# Check namespace
kubectl get ns

# Check pods
kubectl get pods -n raytracer

# Check services
kubectl get svc -n raytracer

# Check PVCs
kubectl get pvc -n raytracer

# Check deployment status
kubectl describe deployment web -n raytracer
kubectl describe deployment worker -n raytracer
```

### Access Applications

#### Web Application (API)
```bash
# Port forward to access
kubectl port-forward -n raytracer svc/web-service 8000:8000

# Access at http://localhost:8000
```

#### MinIO Console
```bash
# Port forward to access
kubectl port-forward -n raytracer svc/minio-console-external 9001:9001

# Access at http://localhost:9001
# Username: minioadmin
# Password: minioadmin
```

#### RabbitMQ Management UI
```bash
# Port forward to access
kubectl port-forward -n raytracer svc/rabbitmq-service 15672:15672

# Access at http://localhost:15672
# Username: guest
# Password: guest
```

## Configuration

### Modify Secrets
Edit `secrets.yaml` to change passwords and API keys:
```bash
kubectl edit secret raytracer-secrets -n raytracer
```

### Modify Configuration
Edit `configmap.yaml` to change configuration:
```bash
kubectl edit configmap raytracer-config -n raytracer
```

### Scale Deployments
```bash
# Scale web deployment to 3 replicas
kubectl scale deployment web --replicas=3 -n raytracer

# Scale worker deployment to 5 replicas
kubectl scale deployment worker --replicas=5 -n raytracer
```

## Storage

### Persistent Volumes
The deployment uses Cinder storage class for persistent volumes:
- **PostgreSQL**: 10Gi volume (postgres-pvc)
- **MinIO**: 50Gi volume (minio-pvc)

Adjust storage sizes in `pvc.yaml` as needed.

## Resources and Limits

Current resource allocation:
- **PostgreSQL**: 256Mi RAM (req), 512Mi (limit); 250m CPU (req), 500m (limit)
- **RabbitMQ**: 256Mi RAM (req), 512Mi (limit); 250m CPU (req), 500m (limit)
- **MinIO**: 512Mi RAM (req), 1Gi (limit); 500m CPU (req), 1000m (limit)
- **Web**: 256Mi RAM (req), 512Mi (limit); 250m CPU (req), 500m (limit) per pod
- **Worker**: 512Mi RAM (req), 1Gi (limit); 500m CPU (req), 1000m (limit) per pod

Adjust in respective deployment files based on your cluster capacity.

## Troubleshooting

### Check pod logs
```bash
kubectl logs -n raytracer <pod-name>
kubectl logs -n raytracer deployment/web
kubectl logs -n raytracer deployment/worker
```

### Describe pod for events
```bash
kubectl describe pod -n raytracer <pod-name>
```

### Check PVC status
```bash
kubectl describe pvc -n raytracer postgres-pvc
kubectl describe pvc -n raytracer minio-pvc
```

### Delete entire deployment
```bash
kubectl delete namespace raytracer
```

## Notes

- Replicas are set to 1 for databases and brokers (PostgreSQL, RabbitMQ, MinIO) for consistency
- Web and worker deployments can be scaled horizontally
- Init containers ensure services start in the correct order
- All secrets should be changed from defaults in production
- Consider using sealed-secrets or external-secrets for secret management in production
- Update image pull policies and tags as needed for your registry
- Add ingress configuration for production access to web application
