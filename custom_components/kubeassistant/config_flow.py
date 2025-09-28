import os
import shutil
from pathlib import Path
import voluptuous as vol
import yaml
from homeassistant import config_entries
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import FileSelector, FileSelectorConfig
from homeassistant.util.ulid import ulid
from homeassistant.helpers.storage import STORAGE_DIR
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "kubeassistant"

class KubeAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    
    async def async_step_user(self, user_input=None):
        errors = {}
        
        if user_input is not None:
            # Validate the custom name
            name = user_input.get("name", "").strip()
            if not name:
                errors["name"] = "required"
            else:
                # Check for duplicate names
                existing_entries = self._async_current_entries()
                existing_names = [entry.title for entry in existing_entries]
                if name in existing_names:
                    errors["name"] = "name_exists"
                
            file_id = user_input.get("kubeconfig_file")
            _LOGGER.debug(f"Received file_id: {file_id}, type: {type(file_id)}")
            
            if not file_id:
                errors["kubeconfig_file"] = "required"
            
            # Only proceed if we have both name and file
            if name and file_id:
                try:
                    # Store the file in Home Assistant's config directory
                    stored_path = await save_uploaded_kubeconfig_file(self.hass, file_id)
                    
                    # Save the stored path in the config entry with custom name
                    return self.async_create_entry(
                        title=name,
                        data={
                            "name": name,
                            "kubeconfig_stored_path": stored_path,
                            "kubeconfig_file_id": file_id  # Keep reference to original
                        }
                    )
                except ValueError as e:
                    _LOGGER.error(f"Invalid kubeconfig file: {e}")
                    errors["base"] = "invalid_file"
                except Exception as e:
                    _LOGGER.error(f"Error processing kubeconfig file: {e}")
                    errors["base"] = "invalid_file"

        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required('name', default="My Kubernetes Cluster"): str,
                vol.Required('kubeconfig_file'): FileSelector(FileSelectorConfig(accept=".yaml,.yml,.conf,.config"))
            }),
            errors=errors
        )

async def save_uploaded_kubeconfig_file(hass: HomeAssistant, uploaded_file_id: str) -> str:
    """Validate the uploaded kubeconfig and move it to the storage directory.

    Return a string representing a path to kubeconfig file.
    Raises ValueError if the file is invalid.
    """

    def _process_upload() -> str:
        with process_uploaded_file(hass, uploaded_file_id) as file_path:
            # Read the file content for validation
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Validate that it's a valid kubeconfig
            try:
                config_data = yaml.safe_load(content)
                
                # Basic validation - check for required kubeconfig fields
                if not isinstance(config_data, dict):
                    raise ValueError("Invalid kubeconfig format: not a valid YAML dictionary")
                    
                required_fields = ['clusters', 'contexts', 'users']
                for field in required_fields:
                    if field not in config_data:
                        raise ValueError(f"Invalid kubeconfig: missing required field '{field}'")
            except yaml.YAMLError as err:
                _LOGGER.debug(err)
                raise ValueError("Invalid kubeconfig: not valid YAML") from err

            dest_path = Path(hass.config.path(STORAGE_DIR, DOMAIN))
            dest_file = dest_path / f"kubeconfig_{ulid()}.yaml"

            _LOGGER.info("Saving uploaded kubeconfig to directory: %s", dest_path)

            # Create parent directory
            dest_file.parent.mkdir(exist_ok=True)
            final_path = shutil.move(file_path, dest_file)
            
            # Set secure permissions  
            os.chmod(final_path, 0o600)
            
            return str(final_path)

    return await hass.async_add_executor_job(_process_upload)