from packages.graph_hub.attachment import attach_cartridge, detach_cartridge
from packages.graph_hub.entitlement import grant_free_entitlement
from packages.graph_hub.installer import install_cartridge, uninstall_cartridge


def test_install_does_not_attach_and_attach_is_read_only():
    grant_free_entitlement("atanor_base_free")
    installed = install_cartridge("atanor_base_free")
    assert installed["local_brain_write"] is False
    attached = attach_cartridge("atanor_base_free")
    assert attached["temporary"] is True
    assert attached["local_brain_write"] is False
    assert detach_cartridge("atanor_base_free")["local_brain_write"] is False
    assert uninstall_cartridge("atanor_base_free")["detached_first"] is True
