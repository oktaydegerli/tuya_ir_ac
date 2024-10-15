from .const import DOMAIN

async def async_setup_entry(hass, entry):
    """Kurulum giriş noktası."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    await hass.config_entries.async_forward_entry_setup(entry, "climate")

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_unload_entry(hass, entry):
    """Kurulum giriş noktasını kaldır."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "climate")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def async_reload_entry(hass, entry):
    """Seçenekler değiştiğinde yapılandırma girişini yeniden yükle."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
