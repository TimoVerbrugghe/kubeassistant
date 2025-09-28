# KubeAssistant

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TimoVerbrugghe&repository=kubeassistant)
<!-- [![GitHub Release](https://img.shields.io/github/release/TimoVerbrugghe/kubeassistant.svg)](https://github.com/TimoVerbrugghe/kubeassistant/releases) -->
<!-- [![License](https://img.shields.io/github/license/TimoVerbrugghe/kubeassistant.svg)](LICENSE) -->

A comprehensive Home Assistant custom integration that provides real-time monitoring and insights for your Kubernetes clusters directly from your Home Assistant dashboard.

## Overview

KubeAssistant transforms your Home Assistant into a powerful Kubernetes monitoring hub by creating sensors for various Kubernetes resources. Monitor your deployments, pods, nodes, and other critical resources with ease, and leverage Home Assistant's automation capabilities to create alerts and responses based on your cluster's health.

## Features

- 🚀 **Multi-Resource Monitoring**: Track Deployments, StatefulSets, DaemonSets, Nodes, Namespaces, and CronJobs
- 📊 **Real-Time Status Updates**: Get live updates on resource health and availability
- 🔐 **Secure Authentication**: Uses your existing kubeconfig files for secure cluster access
- 🏠 **Native HA Integration**: Sensors integrate seamlessly with Home Assistant's entity system
- 🔄 **Multiple Cluster Support**: Connect and monitor multiple Kubernetes clusters simultaneously
- 📱 **Dashboard Ready**: All sensors are ready to use in your Home Assistant dashboards
- 🚨 **Automation Compatible**: Use sensor data to trigger automations and notifications

## Supported Kubernetes Resources

| Resource Type | Status Tracking | Additional Attributes |
|---------------|-----------------|----------------------|
| **Deployments** | Ready/Available replicas | Namespace, Labels, Annotations |
| **StatefulSets** | Ready/Current replicas | Namespace, Labels, Service name |
| **DaemonSets** | Desired/Ready nodes | Namespace, Node selector |
| **Nodes** | Ready/Not Ready status | CPU/Memory capacity, Kubernetes version |
| **Namespaces** | Active/Terminating | Creation timestamp, Labels |
| **CronJobs** | Last schedule time | Schedule, Suspend status |

## Installation

### HACS Installation (Recommended)

1. **Add Custom Repository**:
   - Open HACS in your Home Assistant
   - Go to "Integrations"
   - Click the three dots in the top right corner
   - Select "Custom repositories"
   - Add `https://github.com/TimoVerbrugghe/kubeassistant` as a repository
   - Select "Integration" as the category
   - Click "Add"

2. **Install KubeAssistant**:
   - Search for "KubeAssistant" in HACS
   - Click "Download"
   - Restart Home Assistant

### Manual Installation

1. **Download the Integration**:
   ```bash
   cd /config/custom_components
   git clone https://github.com/TimoVerbrugghe/kubeassistant.git
   mv kubeassistant/custom_components/kubeassistant ./
   ```

2. **Restart Home Assistant**

## Configuration

### Prerequisites

Before configuring KubeAssistant, ensure you have:

- A valid kubeconfig file for your Kubernetes cluster
- Network connectivity from your Home Assistant instance to your Kubernetes API server
- Appropriate RBAC permissions in your cluster (see [RBAC Requirements](#rbac-requirements))

### Adding a Kubernetes Cluster

1. **Navigate to Integrations**:
   - Go to Settings → Devices & Services
   - Click "Add Integration"
   - Search for "KubeAssistant"

2. **Configure Connection**:
   - **Connection Name**: Enter a descriptive name (e.g., "Production Cluster", "Home Lab")
   - **Kubeconfig File**: Upload your cluster's kubeconfig file

3. **Verification**:
   - KubeAssistant will validate your kubeconfig
   - Upon successful validation, sensors will be automatically created
   - Check the integration page to see all discovered resources

### RBAC Requirements

Your kubeconfig should have permissions to read the following resources:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kubeassistant-reader
rules:
- apiGroups: [""]
  resources: ["nodes", "namespaces", "pods"]
  verbs: ["get", "list"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets", "daemonsets"]
  verbs: ["get", "list"]
- apiGroups: ["batch"]
  resources: ["cronjobs"]
  verbs: ["get", "list"]
- apiGroups: ["networking.k8s.io"]
  resources: ["ingresses"]
  verbs: ["get", "list"]
```

## Usage

### Sensor Entities

Once configured, KubeAssistant creates sensors with the following naming convention:
- `sensor.kubeassistant_{cluster_name}_{resource_type}_{resource_name}`

Example sensors:
- `sensor.kubeassistant_production_deployment_nginx`
- `sensor.kubeassistant_homelab_node_worker_01`
- `sensor.kubeassistant_staging_namespace_default`

### Sensor States

| Resource | State Values | Description |
|----------|-------------|-------------|
| Deployments | `0-N` | Number of ready replicas |
| StatefulSets | `0-N` | Number of ready replicas |
| DaemonSets | `0-N` | Number of ready pods |
| Nodes | `Ready`/`NotReady` | Node status |
| Namespaces | `Active`/`Terminating` | Namespace phase |
| CronJobs | `Active`/`Suspended` | Job status |

### Sensor Attributes

Each sensor includes detailed attributes:

```yaml
# Example Deployment sensor attributes
state: 3
attributes:
  available_replicas: 3
  ready_replicas: 3
  desired_replicas: 3
  namespace: default
  labels:
    app: nginx
    version: "1.20"
  annotations:
    deployment.kubernetes.io/revision: "1"
  created: "2024-01-15T10:30:00Z"
  cluster_name: "production"
```

## Dashboard Examples

### Basic Resource Overview

```yaml
type: entities
title: Kubernetes Cluster Status
entities:
  - sensor.kubeassistant_production_deployment_api
  - sensor.kubeassistant_production_deployment_frontend
  - sensor.kubeassistant_production_node_master
  - sensor.kubeassistant_production_node_worker_01
show_header_toggle: false
```

### Deployment Health Cards

```yaml
type: horizontal-stack
cards:
  - type: gauge
    entity: sensor.kubeassistant_production_deployment_nginx
    name: Nginx Replicas
    min: 0
    max: 5
    severity:
      green: 3
      yellow: 1
      red: 0
  - type: gauge
    entity: sensor.kubeassistant_production_deployment_api
    name: API Replicas
    min: 0
    max: 3
```

## Automations

### Alert on Pod Failures

```yaml
alias: "Kubernetes Deployment Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.kubeassistant_production_deployment_api
    below: 1
action:
  - service: notify.mobile_app
    data:
      title: "⚠️ Kubernetes Alert"
      message: "API deployment has {{ states('sensor.kubeassistant_production_deployment_api') }} ready replicas"
```

### Node Down Notification

```yaml
alias: "Kubernetes Node Down"
trigger:
  - platform: state
    entity_id: sensor.kubeassistant_production_node_worker_01
    to: "NotReady"
action:
  - service: persistent_notification.create
    data:
      title: "Kubernetes Node Issue"
      message: "Node worker-01 is not ready. Check cluster immediately."
```

## Troubleshooting

### Common Issues

1. **"Failed to set up KubeAssistant" Error**:
   - Verify kubeconfig file is valid
   - Check network connectivity to Kubernetes API
   - Ensure proper RBAC permissions

2. **No Sensors Created**:
   - Check Home Assistant logs for errors
   - Verify cluster has resources to monitor
   - Confirm kubeconfig context is correct

3. **Sensors Show "Unknown" State**:
   - Check if resources still exist in cluster
   - Verify API server is accessible
   - Review integration logs for connection issues

### Debug Logging

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.kubeassistant: debug
```

### Log Files

Check these locations for detailed logs:
- Home Assistant logs: Settings → System → Logs
- Integration-specific logs: Look for "kubeassistant" entries

## Support

- **Issues**: [GitHub Issues](https://github.com/TimoVerbrugghe/kubeassistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/TimoVerbrugghe/kubeassistant/discussions)
- **Documentation**: This README and inline code comments

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

### v1.0.0
- Initial release
- Support for Deployments, StatefulSets, DaemonSets, Nodes, Namespaces, and CronJobs
- Multi-cluster support
- HACS integration

---

**Made with ❤️ for the Home Assistant community**