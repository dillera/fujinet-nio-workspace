def test_config_nio_hosts_mount_and_64_host_limit(run_amiga_case,
                                                  amiga_environment):
    results = run_amiga_case("config-nio")

    assert "LOAD RC=0" in results["cfg-load.result"]

    accept = results["cfg-accept.result"]
    assert "HOST 3 host:/" in accept
    assert "ERR" not in accept
    drive = "DO0:" if amiga_environment["AMIGA_ENV_ID"] == "wb13" else "DN0:"
    assert f"DRIVE {drive} 11 RO" in accept

    fill = results["cfg-fill.result"]
    assert "HOST 63 tnfs://h59" in fill
    assert "HOST 64" not in fill
    # The 65th add is refused; every other command succeeded.
    assert fill.count("ERR") == 1
    assert "Host list is full" in fill

    # A second run reads the 64 hosts back from the app store.
    reload = results["cfg-reload.result"]
    assert "HOST 0 " in reload
    assert "HOST 63 tnfs://h59" in reload
    assert "HOST 64" not in reload

    # A folder of 300 entries (more than the 200-entry table): ListPages
    # reaches all of them, and the device sorts directories first.
    big = results["cfg-big.result"]
    assert "ENTRY D zdir" in big
    assert big.index("ENTRY D zdir") < big.index("ENTRY F f000.txt")
    for name in ("f299.txt", "f000.txt", "f150.txt"):
        assert f"> select {name}\nOK" in big
    assert "SCRIPT DONE ok=" in big and "err=0" in big

    # The mount picker checks the image against the drive.  hd.adf is HD OFS:
    # WB1.3's DN1: is a fixed DD/FFS endpoint and must refuse it before
    # FMOUNT runs, while HO0: takes it.  Other Workbenches let DN1: take it.
    media = results["cfg-media.result"]
    if amiga_environment["AMIGA_ENV_ID"] == "wb13":
        assert "hd.adf is HD OFS; DN1: cannot take it" in media
        assert "DRIVE HO0: " in media
    else:
        assert "cannot take it" not in media.split("> mount DN0:")[0]
        assert "Nothing selected" not in media, media
        assert "DRIVE DN1: " in media
        if amiga_environment["AMIGA_ENV_ID"] == "wb31":
            # DN0: already runs a DD handler that FFS 40.1 cannot retire, so
            # the picker must refuse HD media on it.
            assert "hd.adf is HD OFS; DN0: cannot take it" in media
