import os
import logging
from kubernetes import client, config
from kubernetes.config import ConfigException
from homeassistant.helpers.entity import Entity
from homeassistant.const import EntityCategory
import tempfile

_LOGGER = logging.getLogger(__name__)
DOMAIN = "kubeassistant"

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor from a config entry."""
    # Get the stored kubeconfig path from config entry
    kubeconfig_path = entry.data.get("kubeconfig_stored_path")
    
    if not kubeconfig_path or not os.path.exists(kubeconfig_path):
        _LOGGER.error(f"Kubeconfig file not found at: {kubeconfig_path}")
        return False
    
    # Test kubeconfig file and create API clients
    try:
        # Create API clients with the specific kubeconfig
        api_clients = await hass.async_add_executor_job(
            _create_api_clients, kubeconfig_path
        )
        
        if not api_clients:
            _LOGGER.error("Failed to create Kubernetes API clients")
            return False
            
        v1, apps_v1, batch_v1, networking_v1 = api_clients
        
    except Exception as e:
        _LOGGER.error(f"Failed to initialize Kubernetes API clients: {e}")
        return False

    # Fetch all resources to create sensors
    try:
        resources = await hass.async_add_executor_job(
            _fetch_all_resources, v1, apps_v1, batch_v1, networking_v1
        )
        
        if not resources:
            _LOGGER.error("Failed to fetch Kubernetes resources")
            return False
            
    except Exception as e:
        _LOGGER.error(f"Failed to fetch Kubernetes resources: {e}")
        return False

    sensors = []
    deployments, statefulsets, daemonsets, namespaces, nodes, cronjobs = resources

    # Create sensors for each resource type
    for dep in deployments:
        sensors.append(KubeDeploymentSensor(dep, kubeconfig_path, entry.entry_id))
    for sts in statefulsets:
        sensors.append(KubeStatefulSetSensor(sts, kubeconfig_path, entry.entry_id))
    for ds in daemonsets:
        sensors.append(KubeDaemonSetSensor(ds, kubeconfig_path, entry.entry_id))
    for ns in namespaces:
        sensors.append(KubeNamespaceSensor(ns, kubeconfig_path, entry.entry_id))
    for node in nodes:
        sensors.append(KubeNodeSensor(node, kubeconfig_path, entry.entry_id))
    for cj in cronjobs:
        sensors.append(KubeCronJobSensor(cj, kubeconfig_path, entry.entry_id))

    async_add_entities(sensors)
    _LOGGER.info(f"Successfully created {len(sensors)} Kubernetes sensors")
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    # Clean up stored data
    if entry.entry_id in hass.data.get("kubeassistant", {}):
        hass.data["kubeassistant"].pop(entry.entry_id)
    return True

def _create_api_clients(kubeconfig_path):
    """Create Kubernetes API clients with specific kubeconfig."""
    try:
        # Load configuration from the specific kubeconfig file
        config.load_kube_config(config_file=kubeconfig_path)
        
        # Create API clients
        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        batch_v1 = client.BatchV1Api()
        networking_v1 = client.NetworkingV1Api()
        
        # Test the connection with a simple API call
        # Use the correct method name for testing connectivity
        v1.list_namespace(limit=1)
        
        return (v1, apps_v1, batch_v1, networking_v1)
        
    except ConfigException as e:
        _LOGGER.error(f"Kubernetes config error: {e}")
        return None
    except Exception as e:
        _LOGGER.error(f"Failed to create Kubernetes API clients: {e}")
        return None

def _fetch_all_resources(v1, apps_v1, batch_v1, networking_v1):
    """Fetch all Kubernetes resources."""
    try:
        deployments = apps_v1.list_deployment_for_all_namespaces()
        statefulsets = apps_v1.list_stateful_set_for_all_namespaces()
        daemonsets = apps_v1.list_daemon_set_for_all_namespaces()
        namespaces = v1.list_namespace()
        nodes = v1.list_node()
        cronjobs = batch_v1.list_cron_job_for_all_namespaces()
        
        return (
            deployments.items, statefulsets.items, daemonsets.items,
            namespaces.items, nodes.items, cronjobs.items
        )
        
    except Exception as e:
        _LOGGER.error(f"Failed to fetch resources: {e}")
        return None

def _convert_memory_to_gb(memory_str):
    """Convert Kubernetes memory string to GB.
    
    Supports formats like:
    - 5368504Ki (Kibibytes)
    - 5242880Mi (Mebibytes)  
    - 5120Gi (Gibibytes)
    - 5368709120 (bytes)
    """
    if not memory_str:
        return None
        
    memory_str = str(memory_str).strip()
    
    try:
        if memory_str.endswith('Ki'):
            # Kibibytes to GiB: 1 Ki = 1024 bytes; 1 GiB = 1,073,741,824 bytes
            kibibytes = float(memory_str[:-2])
            giB = (kibibytes * 1024) / 1_073_741_824
            return round(giB)
        elif memory_str.endswith('Mi'):
            # Mebibytes to GiB: 1 Mi = 1024^2 bytes
            mebibytes = float(memory_str[:-2])
            giB = (mebibytes * 1024 * 1024) / 1_073_741_824
            return round(giB)
        elif memory_str.endswith('Gi'):
            # Gibibytes to GiB: 1 Gi = 1024^3 bytes
            gibibytes = float(memory_str[:-2])
            giB = (gibibytes * 1024 * 1024 * 1024) / 1_073_741_824
            return round(giB)
        else:
            # Assume bytes
            bytes_val = float(memory_str)
            giB = bytes_val / 1_073_741_824
            return round(giB)
    except (ValueError, TypeError):
        _LOGGER.warning(f"Failed to convert memory value: {memory_str}")
        return None

# --- Base Sensor Class ---

class KubeResourceSensor(Entity):
    """Base class for Kubernetes resource sensors."""
    
    def __init__(self, resource, kubeconfig_path, entry_id):
        self._resource = resource
        self._kubeconfig_path = kubeconfig_path
        self._entry_id = entry_id
        self._available = True
        self._api_clients = None
    
    @property
    def available(self):
        """Return if entity is available."""
        return self._available
    
    @property
    def entity_category(self):
        """Return the entity category."""
        return EntityCategory.DIAGNOSTIC
    
    @property
    def should_poll(self):
        """Return True if entity has to be polled for state."""
        return True
    
    def _get_api_clients(self):
        """Get fresh API clients for this sensor."""
        if not self._api_clients:
            self._api_clients = _create_api_clients(self._kubeconfig_path)
        return self._api_clients
    
    async def _safe_api_call(self, api_type, func_name, *args):
        """Safely call Kubernetes API with error handling."""
        try:
            clients = await self.hass.async_add_executor_job(self._get_api_clients)
            if not clients:
                self._available = False
                return None
                
            v1, apps_v1, batch_v1, networking_v1 = clients
            
            # Select the appropriate API client
            api_map = {
                'v1': v1,
                'apps_v1': apps_v1,
                'batch_v1': batch_v1,
                'networking_v1': networking_v1
            }
            
            api = api_map.get(api_type)
            if not api:
                _LOGGER.error(f"Unknown API type: {api_type}")
                return None
                
            func = getattr(api, func_name)
            result = await self.hass.async_add_executor_job(func, *args)
            self._available = True
            return result
            
        except Exception as e:
            _LOGGER.warning(f"Failed to update {self.name}: {e}")
            self._available = False
            # Reset API clients on error to force recreation
            self._api_clients = None
            return None

# --- Sensor Classes ---

class KubeDeploymentSensor(KubeResourceSensor):
    def __init__(self, dep, kubeconfig_path, entry_id):
        super().__init__(dep, kubeconfig_path, entry_id)
        self._dep = dep

    @property
    def name(self):
        return f"Deployment {self._dep.metadata.namespace}/{self._dep.metadata.name}"

    @property
    def unique_id(self):
        return f"k8s_deployment_{self._dep.metadata.uid}"

    @property
    def state(self):
        # Determine deployment status based on conditions and replicas
        if self._dep.status.conditions:
            for condition in self._dep.status.conditions:
                if condition.type == "Progressing" and condition.status == "False":
                    return "Failed"
                elif condition.type == "Available" and condition.status == "False":
                    return "Progressing"
        
        # Check if deployment is ready
        desired_replicas = self._dep.status.replicas or 0
        available_replicas = self._dep.status.available_replicas or 0
        
        if desired_replicas == 0:
            return "Stopped"
        elif available_replicas == desired_replicas:
            return "Running"
        else:
            return "Progressing"

    @property
    def unit_of_measurement(self):
        return None

    @property
    def icon(self):
        return "mdi:application-brackets"

    @property
    def extra_state_attributes(self):
        return {
            "namespace": self._dep.metadata.namespace,
            "replicas": self._dep.status.replicas,
            "updated_replicas": self._dep.status.updated_replicas,
            "unavailable_replicas": self._dep.status.unavailable_replicas,
            "resource_type": "Deployment",
        }

    async def async_update(self):
        dep = await self._safe_api_call(
            "apps_v1",
            "read_namespaced_deployment",
            self._dep.metadata.name,
            self._dep.metadata.namespace,
        )
        if dep:
            self._dep = dep

class KubeStatefulSetSensor(KubeResourceSensor):
    def __init__(self, sts, kubeconfig_path, entry_id):
        super().__init__(sts, kubeconfig_path, entry_id)
        self._sts = sts

    @property
    def name(self):
        return f"StatefulSet {self._sts.metadata.namespace}/{self._sts.metadata.name}"

    @property
    def unique_id(self):
        return f"k8s_statefulset_{self._sts.metadata.uid}"

    @property
    def state(self):
        # Determine StatefulSet status based on replicas
        desired_replicas = self._sts.status.replicas or 0
        ready_replicas = self._sts.status.ready_replicas or 0
        current_replicas = self._sts.status.current_replicas or 0
        updated_replicas = self._sts.status.updated_replicas or 0
        
        if desired_replicas == 0:
            return "Stopped"
        elif ready_replicas == desired_replicas and updated_replicas == desired_replicas:
            return "Running"
        elif current_replicas > 0:
            return "Progressing"
        else:
            return "Failed"

    @property
    def unit_of_measurement(self):
        return None

    @property
    def icon(self):
        return "mdi:application-brackets"

    @property
    def extra_state_attributes(self):
        return {
            "namespace": self._sts.metadata.namespace,
            "replicas": self._sts.status.replicas,
            "ready_replicas": self._sts.status.ready_replicas,
            "current_replicas": self._sts.status.current_replicas,
            "updated_replicas": self._sts.status.updated_replicas,
            "resource_type": "StatefulSet",
        }

    async def async_update(self):
        sts = await self._safe_api_call(
            "apps_v1",
            "read_namespaced_stateful_set",
            self._sts.metadata.name,
            self._sts.metadata.namespace,
        )
        if sts:
            self._sts = sts

class KubeNamespaceSensor(KubeResourceSensor):
    def __init__(self, ns, kubeconfig_path, entry_id):
        super().__init__(ns, kubeconfig_path, entry_id)
        self._ns = ns

    @property
    def name(self):
        return f"Namespace {self._ns.metadata.name}"

    @property
    def unique_id(self):
        return f"k8s_namespace_{self._ns.metadata.uid}"

    @property
    def state(self):
        return self._ns.status.phase

    @property
    def icon(self):
        return "mdi:folder-outline"

    @property
    def extra_state_attributes(self):
        return {
            "labels": self._ns.metadata.labels,
            "creation_timestamp": str(self._ns.metadata.creation_timestamp),
            "status": self._ns.status.phase,
            "resource_type": "Namespace",
        }

    async def async_update(self):
        ns = await self._safe_api_call(
            "v1",
            "read_namespace",
            self._ns.metadata.name,
        )
        if ns:
            self._ns = ns

class KubeNodeSensor(KubeResourceSensor):
    def __init__(self, node, kubeconfig_path, entry_id):
        super().__init__(node, kubeconfig_path, entry_id)
        self._node = node

    @property
    def name(self):
        return f"Node {self._node.metadata.name}"

    @property
    def unique_id(self):
        return f"k8s_node_{self._node.metadata.uid}"

    @property
    def state(self):
        return "Ready" if any(
            c.type == "Ready" and c.status == "True" for c in self._node.status.conditions
        ) else "NotReady"

    @property
    def icon(self):
        return "mdi:server"

    @property
    def extra_state_attributes(self):
        # Extract IP address from node addresses
        ip_address = None
        if self._node.status.addresses:
            for addr in self._node.status.addresses:
                if addr.type == "InternalIP":
                    ip_address = addr.address
                    break
            # Fallback to first address if no InternalIP found
            if not ip_address and self._node.status.addresses:
                ip_address = self._node.status.addresses[0].address
        
        # Extract CPU and Memory from capacity and allocatable
        cpu_capacity = self._node.status.capacity.get("cpu") if self._node.status.capacity else None
        memory_capacity_raw = self._node.status.capacity.get("memory") if self._node.status.capacity else None
        memory_allocatable_raw = self._node.status.allocatable.get("memory") if self._node.status.allocatable else None
        
        # Convert memory values to GB
        memory_capacity_gb = _convert_memory_to_gb(memory_capacity_raw)
        memory_allocatable_gb = _convert_memory_to_gb(memory_allocatable_raw)
        
        return {
            "ip_address": ip_address,
            "CPU Cores": f"{cpu_capacity} cores",
            "Total Memory (GB)": f"{memory_capacity_gb} GB",
            "Free Memory (GB)": f"{memory_allocatable_gb} GB",
            "labels": self._node.metadata.labels,
            "addresses": [a.address for a in self._node.status.addresses] if self._node.status.addresses else [],
            "capacity": self._node.status.capacity,
            "allocatable": self._node.status.allocatable,
            "conditions": [{"type": c.type, "status": c.status} for c in self._node.status.conditions] if self._node.status.conditions else [],
            "resource_type": "Node",
        }

    async def async_update(self):
        node = await self._safe_api_call(
            "v1",
            "read_node",
            self._node.metadata.name,
        )
        if node:
            self._node = node

class KubeDaemonSetSensor(KubeResourceSensor):
    def __init__(self, ds, kubeconfig_path, entry_id):
        super().__init__(ds, kubeconfig_path, entry_id)
        self._ds = ds

    @property
    def name(self):
        return f"DaemonSet {self._ds.metadata.namespace}/{self._ds.metadata.name}"

    @property
    def unique_id(self):
        return f"k8s_daemonset_{self._ds.metadata.uid}"

    @property
    def state(self):
        # Determine DaemonSet status based on desired vs ready
        desired_scheduled = self._ds.status.desired_number_scheduled or 0
        number_ready = self._ds.status.number_ready or 0
        number_available = self._ds.status.number_available or 0
        
        if desired_scheduled == 0:
            return "Stopped"
        elif number_ready == desired_scheduled and number_available == desired_scheduled:
            return "Running"
        elif number_ready > 0:
            return "Progressing"
        else:
            return "Failed"

    @property
    def unit_of_measurement(self):
        return None

    @property
    def icon(self):
        return "mdi:application-brackets"

    @property
    def extra_state_attributes(self):
        return {
            "namespace": self._ds.metadata.namespace,
            "desired_number_scheduled": self._ds.status.desired_number_scheduled,
            "current_number_scheduled": self._ds.status.current_number_scheduled,
            "number_ready": self._ds.status.number_ready,
            "number_available": self._ds.status.number_available,
            "resource_type": "DaemonSet",
        }

    async def async_update(self):
        ds = await self._safe_api_call(
            "apps_v1",
            "read_namespaced_daemon_set",
            self._ds.metadata.name,
            self._ds.metadata.namespace,
        )
        if ds:
            self._ds = ds

class KubeCronJobSensor(KubeResourceSensor):
    def __init__(self, cj, kubeconfig_path, entry_id):
        super().__init__(cj, kubeconfig_path, entry_id)
        self._cj = cj

    @property
    def name(self):
        return f"CronJob {self._cj.metadata.namespace}/{self._cj.metadata.name}"

    @property
    def unique_id(self):
        return f"k8s_cronjob_{self._cj.metadata.uid}"

    @property
    def state(self):
        return str(self._cj.status.last_schedule_time) if self._cj.status.last_schedule_time else "Never"

    @property
    def icon(self):
        return "mdi:clock-outline"

    @property
    def extra_state_attributes(self):
        return {
            "namespace": self._cj.metadata.namespace,
            "schedule": self._cj.spec.schedule,
            "suspend": self._cj.spec.suspend,
            "active": [a.name for a in self._cj.status.active] if self._cj.status.active else [],
            "resource_type": "CronJob",
        }

    async def async_update(self):
        cj = await self._safe_api_call(
            "batch_v1",
            "read_namespaced_cron_job",
            self._cj.metadata.name,
            self._cj.metadata.namespace,
        )
        if cj:
            self._cj = cj