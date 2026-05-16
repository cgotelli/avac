import os
from pathlib import Path
import tarfile

import numpy as np

from gui.services import (
    RasterData,
    build_avac_configuration,
    build_local_claw_env,
    derive_notebook_pressure_field,
    derive_notebook_profile_axes,
    extract_avac_files,
    latest_result_directory,
    list_fgout_frames,
    list_result_directories,
    load_fgmax_results,
    read_ascii_raster,
    write_claw_qinit_xyz,
    write_claw_topography_ascii,
)


def test_read_ascii_raster_parses_basic_grid(tmp_path: Path) -> None:
    asc = tmp_path / "demo.asc"
    asc.write_text(
        "\n".join(
            [
                "ncols 3",
                "nrows 2",
                "xllcorner 100",
                "yllcorner 200",
                "cellsize 10",
                "NODATA_value -9999",
                "1 2 3",
                "4 -9999 6",
            ]
        ),
        encoding="utf-8",
    )

    raster = read_ascii_raster(asc)

    assert raster.metadata["ncols"] == 3
    assert raster.metadata["nrows"] == 2
    assert raster.metadata["xmin"] == 100
    assert raster.metadata["ymin"] == 200
    assert raster.metadata["nodata_value"] == -9999
    assert raster.z.shape == (2, 3)
    assert np.isnan(raster.z).sum() == 1


def test_build_avac_configuration_maps_expected_fields() -> None:
    params = {
        "computation": {"t_max": 120, "nb_simul": 40, "domain_cell": 2, "cfl_target": 0.4, "cfl_max": 0.8},
        "rheology": {"model": "Voellmy", "rho": 300, "mu": 0.25, "xi": 1800, "u_cr": 0.1, "beta": 1.1},
        "output": {"output_format": "binary32", "verbosity": 1, "delta_t": 2},
        "animation": {"n_out": 60, "variable": "depth"},
    }
    dem_meta = {
        "xmin": 10.0,
        "xmax": 20.0,
        "ymin": 30.0,
        "ymax": 40.0,
        "ncols": 5,
        "nrows": 4,
        "cellsize": 2.0,
        "nodata_value": -9999.0,
    }

    cfg = build_avac_configuration(params, dem_meta)

    assert cfg["computation"]["t_max"] == 120
    assert cfg["rheology"]["mu"] == 0.25
    assert cfg["output"]["delta_t"] == 2
    assert cfg["animation"]["n_out"] == 60
    assert cfg["dem_extent"] == {
        "xmin": 10.0,
        "xmax": 20.0,
        "ymin": 30.0,
        "ymax": 40.0,
        "nbx": 5,
        "nby": 4,
        "cell_size": 2.0,
        "nodata_value": -9999.0,
    }
    assert cfg["file_names"] == {
        "topofile": "topography.asc",
        "initiation_file": "init.xyz",
        "type_dem": 3,
        "type_init": 1,
    }


def test_write_claw_topography_ascii_and_qinit_order(tmp_path: Path) -> None:
    raster = RasterData(
        x=np.array([0.0, 1.0]),
        y=np.array([10.0, 11.0]),
        z=np.array([[1.0, 2.0], [3.0, np.nan]]),
        metadata={
            "xmin": 0.0,
            "ymin": 10.0,
            "cellsize": 1.0,
            "nodata_value": -9999.0,
        },
    )

    topo_path = tmp_path / "topography.asc"
    write_claw_topography_ascii(topo_path, raster)
    lines = topo_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("ncols 2")
    assert lines[1].startswith("nrows 2")
    assert lines[5].startswith("NODATA_value -9999")
    # North row (y=11) is written first.
    assert lines[6].split() == ["3", "-9999"]
    assert lines[7].split() == ["1", "2"]

    q = np.array([[10.0, 20.0], [30.0, 40.0]])
    qinit_path = tmp_path / "init.xyz"
    write_claw_qinit_xyz(qinit_path, raster.x, raster.y, q)
    qlines = qinit_path.read_text(encoding="utf-8").splitlines()
    # qinit must start from NW point and sweep west->east, then go south.
    assert qlines[0] == "0 11 30"
    assert qlines[1] == "1 11 40"
    assert qlines[2] == "0 10 10"
    assert qlines[3] == "1 10 20"


def test_extract_avac_files_promotes_nested_files_folder(tmp_path: Path) -> None:
    archive = tmp_path / "files.tar.gz"
    source_root = tmp_path / "source"
    nested = source_root / "files"
    nested.mkdir(parents=True)
    (nested / "Makefile").write_text("all:\n\techo ok\n", encoding="utf-8")
    (nested / "setrun.py").write_text("print('ok')\n", encoding="utf-8")
    (nested / "setprob.f90").write_text("program x\nend program\n", encoding="utf-8")

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(nested / "Makefile", arcname="files/Makefile")
        tar.add(nested / "setrun.py", arcname="files/setrun.py")
        tar.add(nested / "setprob.f90", arcname="files/setprob.f90")

    project = tmp_path / "project"
    project.mkdir()
    extract_avac_files(archive, project)

    assert (project / "Makefile").exists()
    assert (project / "setrun.py").exists()
    assert (project / "setprob.f90").exists()


def test_build_local_claw_env_sets_python_and_pythonpath(tmp_path: Path) -> None:
    project = tmp_path / "project"
    claw_root = project / ".vendor" / "clawpack-src"
    claw_root.mkdir(parents=True)

    fake_python = project / "env" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text("", encoding="utf-8")

    base_env = {
        "PATH": os.pathsep.join(["/usr/local/bin", "/usr/bin"]),
        "PYTHONPATH": os.pathsep.join(["/custom/lib"]),
    }

    old_claw_root = os.environ.get("AVAC_CLAW_ROOT")
    os.environ["AVAC_CLAW_ROOT"] = str(claw_root)
    try:
        env = build_local_claw_env(base_env, project, python_executable=str(fake_python))
    finally:
        if old_claw_root is None:
            os.environ.pop("AVAC_CLAW_ROOT", None)
        else:
            os.environ["AVAC_CLAW_ROOT"] = old_claw_root

    assert env["CLAW"] == str(claw_root.resolve())
    assert env["CLAW_PYTHON"] == str(fake_python)
    assert env["PATH"].split(os.pathsep)[0] == str(fake_python.parent)
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(claw_root.resolve())
    assert "/custom/lib" in env["PYTHONPATH"].split(os.pathsep)


def test_load_fgmax_results_parses_rectangular_grid_and_pressure(tmp_path: Path) -> None:
    output = tmp_path / "_output"
    output.mkdir()
    rows = np.array(
        [
            [0.0, 0.0, 1, 100.0, 0.5, 2.0, 1.0, 2.0, 3.0],
            [1.0, 0.0, 1, 110.0, 1.0, 4.0, 1.0, 2.0, 3.0],
            [0.0, 1.0, 1, 90.0, 2.0, 0.0, 1.0, 2.0, 3.0],
            [1.0, 1.0, 1, 80.0, 0.0, 5.0, 1.0, 2.0, 3.0],
        ],
        dtype=float,
    )
    np.savetxt(output / "fgmax0001.txt", rows, fmt="%.6f")

    fg = load_fgmax_results(output, rho=300.0)

    np.testing.assert_allclose(fg.x, np.array([0.0, 1.0]))
    np.testing.assert_allclose(fg.y, np.array([0.0, 1.0]))
    np.testing.assert_allclose(fg.topography, np.array([[100.0, 110.0], [90.0, 80.0]]))
    np.testing.assert_allclose(fg.depth, np.array([[0.5, 1.0], [2.0, 0.0]]))
    np.testing.assert_allclose(fg.velocity, np.array([[2.0, 4.0], [0.0, 5.0]]))
    np.testing.assert_allclose(fg.pressure, np.array([[0.6, 2.4], [0.0, 3.75]]))
    assert fg.depth_time is not None
    np.testing.assert_allclose(fg.depth_time, np.ones((2, 2)))


def test_result_directory_listing_and_latest_selection(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    out1 = project / "_output"
    out2 = project / "_output_case2"
    out1.mkdir()
    out2.mkdir()

    data = np.array([[0.0, 0.0, 1, 100.0, 0.1, 1.0, 0.0, 0.0, 0.0]], dtype=float)
    np.savetxt(out1 / "fgmax0001.txt", data, fmt="%.6f")
    np.savetxt(out2 / "fgmax0001.txt", data, fmt="%.6f")

    old = 1_700_000_000
    new = old + 3600
    os.utime(out1 / "fgmax0001.txt", (old, old))
    os.utime(out2 / "fgmax0001.txt", (new, new))

    listed = list_result_directories(project, configured_output_dir="_output")
    assert out1.resolve() in listed
    assert out2.resolve() in listed
    assert latest_result_directory(project, configured_output_dir="_output") == out2.resolve()


def test_derive_notebook_profile_axes_uses_dem_extent_when_valid() -> None:
    x = np.array([0.0, 2.0, 4.0])
    y = np.array([10.0, 12.0, 14.0, 16.0])
    dem_extent = {"xmin": 0.0, "xmax": 6.0, "ymin": 10.0, "ymax": 18.0}

    x_axis, y_axis = derive_notebook_profile_axes(x, y, dem_extent)

    np.testing.assert_allclose(x_axis, np.array([0.0, 3.0, 6.0]))
    np.testing.assert_allclose(y_axis, np.array([10.0, 12.66666667, 15.33333333, 18.0]))


def test_derive_notebook_profile_axes_falls_back_on_invalid_extent() -> None:
    x = np.array([1.0, 2.0])
    y = np.array([3.0, 4.0])
    dem_extent = {"xmin": 0.0, "xmax": 0.0, "ymin": 1.0, "ymax": 2.0}

    x_axis, y_axis = derive_notebook_profile_axes(x, y, dem_extent)

    np.testing.assert_allclose(x_axis, x)
    np.testing.assert_allclose(y_axis, y)


def test_derive_notebook_pressure_field_matches_masked_array_data_behavior() -> None:
    depth = np.array([[0.0, 0.002], [0.5, 1.0]])
    velocity = np.array([[0.0, 4.0], [5.0, 0.0]])

    pressure = derive_notebook_pressure_field(depth, velocity, rho=300.0)

    # Unmasked values should match the physical formula.
    assert np.isclose(pressure[0, 1], 2.4)
    assert np.isclose(pressure[1, 0], 3.75)


def test_list_fgout_frames_reads_frame_numbers_and_times(tmp_path: Path) -> None:
    output = tmp_path / "_output"
    output.mkdir()

    (output / "fgout0001.t0003").write_text(" 3.00000000E+00    time\n", encoding="utf-8")
    (output / "fgout0001.t0001").write_text(" 0.00000000E+00    time\n", encoding="utf-8")
    (output / "fgout0001.t0002").write_text(" 1.50000000E+00    time\n", encoding="utf-8")
    (output / "fgout0002.t0001").write_text(" 9.90000000E+00    time\n", encoding="utf-8")

    frames = list_fgout_frames(output, fgno=1)

    assert [item.frame_no for item in frames] == [1, 2, 3]
    np.testing.assert_allclose([item.time for item in frames], [0.0, 1.5, 3.0])
