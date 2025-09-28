from kubernetes import config, client
from homeassistant.core import HomeAssistant
import os
import logging

DOMAIN = "kubeassistant"

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up KubeAssistant from a config entry."""
    kubeconfig_path = entry.data["kubeconfig_stored_path"]
    
    try:
        # Load the kubeconfig and create API clients in executor to avoid blocking
        def _setup_kubernetes_clients():
            """Set up Kubernetes clients (runs in executor to avoid blocking calls)."""
            config.load_kube_config(config_file=kubeconfig_path)
            return {
                "v1": client.CoreV1Api(),
                "apps_v1": client.AppsV1Api(),
                "batch_v1": client.BatchV1Api(),
                "networking_v1": client.NetworkingV1Api(),
            }

        # Execute the Kubernetes client setup in an executor
        api_clients = await hass.async_add_executor_job(_setup_kubernetes_clients)

        # Store API clients for use in sensors
        hass.data[DOMAIN] = api_clients

        # Set up the sensor platform
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
        
        _LOGGER.info(f"Successfully set up KubeAssistant with kubeconfig: {kubeconfig_path}")
        return True
        
    except Exception as e:
        _LOGGER.error(f"Failed to set up KubeAssistant: {e}")
        return False

async def async_unload_entry(hass, entry):
    """Handle removal of an entry."""
    # Unload the sensor platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    
    if unload_ok:
        # Clean up stored data
        hass.data.pop(DOMAIN, None)
        
        # Optionally remove the stored kubeconfig file
        kubeconfig_path = entry.data.get("kubeconfig_stored_path")
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            try:
                await hass.async_add_executor_job(os.remove, kubeconfig_path)
                _LOGGER.info(f"Removed kubeconfig file: {kubeconfig_path}")
            except Exception as e:
                _LOGGER.warning(f"Failed to remove kubeconfig file: {kubeconfig_path}, error: {e}")
    
    return unload_ok