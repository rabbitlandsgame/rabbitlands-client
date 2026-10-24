"""Capacity regressions using real budget checks and measured phase witnesses.

The hosted witnesses are from failed Actions run 40116956902, selected commit
908d36960cd833ace03d939f2b334d98bbbcb0f7. They are cumulative unique file bytes,
not compressed downloads or game-package sizes. Local SDK/import/VRAM values
are explicit sizing fixtures, not a claim about a future hosted cache hit.
No engine, network, compiler, or multi-gigabyte fixture is needed.
"""
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import client_release
import release_native_runtime
import release_storage
import runner_source


HOSTED = {
    "windows": {"preflight": 958_526_234, "source_peak": 10_595_213_560,
                "post_editor": 9_604_862_281, "compile_deficit": 826_087_753},
    "linux": {"preflight": 856_094_123, "source_peak": 10_492_780_678,
              "post_editor": 9_502_429_389, "compile_deficit": 723_654_861},
}
# Metadata-only local observations, 2026-10-24. The SDK count is RUSTUP_HOME
# alone: using it does not take credit for a larger unmeasured hosted saving.
LOCAL_RUSTUP_BYTES = 621_105_348
LOCAL_IMPORTED_BYTES = 907_431_681
LOCAL_VRAM_BYTES = 804_018_233
LOCAL_WARM_CACHE_LOWER_BOUND = LOCAL_IMPORTED_BYTES + LOCAL_VRAM_BYTES
# Exact read-only candidate sizing after excluding all 312 prepared-source
# inputs: map-retirement-candidate-sizing.json, 2,807 source-only files. The
# real runner must independently verify candidates and guards before deletion.
MAP_RETIREMENT_BYTES = 1_156_177_456
USABLE = 12_000_000_000
COMPILER = 3_221_225_472
GIB = 1_073_741_824


@pytest.fixture
def metered_budget(tmp_path, monkeypatch):
    state = SimpleNamespace(used=0, free=100_000_000_000)
    # The production DiskBudget and physical-free guard remain real. Inject
    # measured cumulative bytes instead of allocating a whole game checkout.
    monkeypatch.setattr(release_storage, "unique_bytes", lambda roots, **kwargs: state.used)
    monkeypatch.setattr(release_storage.shutil, "disk_usage",
                        lambda root: SimpleNamespace(free=state.free))
    return state, release_storage.DiskBudget([tmp_path])


def test_capacity_policy_keeps_compiler_reservation_and_os_margin():
    assert release_storage.RUNNER_BYTES == 14_000_000_000
    assert release_storage.RESERVE_BYTES == 2_000_000_000
    assert release_native_runtime.BUILD_RESERVE_BYTES == COMPILER
    assert runner_source.BATCH_BYTES == 134_217_728
    assert client_release.PART_BYTES == 268_435_456


@pytest.mark.parametrize("platform", HOSTED)
def test_original_post_asset_compiler_forecast_reproduces_hosted_failure(platform, metered_budget):
    state, budget = metered_budget
    state.used = HOSTED[platform]["post_editor"]
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("original late native compile", COMPILER)
    assert state.used + COMPILER - USABLE == HOSTED[platform]["compile_deficit"]
    assert budget.samples[-1]["additional"] == COMPILER
    # A failed check is still part of the in-memory budget, even though the
    # runner's last successfully written disk receipt predates that check.
    assert budget.planned_peak == state.used + COMPILER


@pytest.mark.parametrize("platform", HOSTED)
def test_restored_asset_cache_can_overlap_tiny_native_prewarm(platform, metered_budget):
    state, budget = metered_budget
    state.used = HOSTED[platform]["preflight"] + LOCAL_WARM_CACHE_LOWER_BOUND
    budget.check("preflight with restored cache", 7_000_000_000)
    budget.check("native prewarm before game assets", COMPILER)
    assert budget.samples[-1]["bytes"] + COMPILER < USABLE


@pytest.mark.parametrize("platform", HOSTED)
def test_sdk_retirement_allows_source_archive_with_same_warm_cache(platform, metered_budget):
    state, budget = metered_budget
    state.used = HOSTED[platform]["source_peak"] + LOCAL_WARM_CACHE_LOWER_BOUND
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("source proof before SDK retirement")
    state.used -= LOCAL_RUSTUP_BYTES
    budget.check("source proof after SDK retirement")
    # Source streaming is incremental, not a second complete compressed tree.
    budget.check("conservative extra source batch", runner_source.BATCH_BYTES)


@pytest.mark.parametrize("platform", HOSTED)
def test_source_ready_one_gib_reservation_is_distinct_from_first_export(platform, metered_budget):
    state, budget = metered_budget
    state.used = (HOSTED[platform]["post_editor"] - LOCAL_RUSTUP_BYTES
                  + LOCAL_WARM_CACHE_LOWER_BOUND)
    budget.check("warm source ready", GIB)
    assert USABLE - state.used - GIB > 0
    # A 1.5GB first-export reservation would fail if map retirement waited
    # until after that export. This is an ordering regression, not a reason
    # to lower the reservation or restore cache after all build activity.
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("first export before map retirement", 1_500_000_000)
    state.used -= MAP_RETIREMENT_BYTES
    budget.check("first export after guarded map retirement", 1_500_000_000)


@pytest.mark.parametrize("platform", HOSTED)
def test_native_prewarm_must_not_retain_compiler_scratch_into_full_source(platform, metered_budget):
    state, budget = metered_budget
    state.used = HOSTED[platform]["post_editor"] - LOCAL_RUSTUP_BYTES
    budget.check("source without compiler scratch")
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("compiler scratch retained with assets", COMPILER)


def test_capacity_boundary_is_exact_and_free_space_is_independent(metered_budget):
    state, budget = metered_budget
    state.used = USABLE - COMPILER
    state.free = release_storage.RESERVE_BYTES + COMPILER
    budget.check("exact compiler boundary", COMPILER)
    state.used += 1
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("one byte too much", COMPILER)
    state.used = 1
    state.free -= 1
    with pytest.raises(ValueError, match="insufficient free space"):
        budget.check("unrelated host usage consumed free reserve", COMPILER)


def test_temporary_guard_copy_needs_its_full_bytes_even_if_link_is_expected(metered_budget):
    state, budget = metered_budget
    # An arbitrary non-rounded fixture proves the budget cannot waive the
    # cross-volume copy merely because the common same-volume path links it.
    editor_bytes = 153_865_573
    state.used = USABLE - editor_bytes
    budget.check("temporary final-PCK editor", editor_bytes)
    state.used += 1
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("temporary final-PCK editor", editor_bytes)


def test_archive_part_is_reserved_before_open_and_does_not_require_whole_archive(tmp_path, metered_budget):
    state, budget = metered_budget
    state.used = USABLE - client_release.PART_BYTES + 1
    with pytest.raises(ValueError, match="disk budget exceeded"):
        with release_storage.PartWriter(tmp_path / "payload", "", client_release.PART_BYTES,
                                        budget=budget) as writer:
            writer.write(b"not written")
    assert not list(tmp_path.glob("payload.*"))
    # Small part bytes exercise actual disposal between acknowledgements;
    # the separate production-size boundary above prevents a giant fixture.
    state.used = USABLE - 13
    accepted = []
    def accept(path, row):
        assert list(tmp_path.glob("payload.*")) == [path]
        accepted.append(path.read_bytes())
    with release_storage.PartWriter(tmp_path / "payload", "", 13, accept, budget) as writer:
        writer.write(b"x" * 35)
    assert b"".join(accepted) == b"x" * 35
    assert [len(part) for part in accepted] == [13, 13, 9]
    assert not list(tmp_path.glob("payload.*"))


def test_asset_cache_save_reserves_second_copy_only_after_source_and_stage_release(metered_budget):
    state, budget = metered_budget
    cache = LOCAL_WARM_CACHE_LOWER_BOUND
    archive = cache + 67_108_864
    # Measured hosted source + restored cache cannot overlap a full cache
    # upload archive. Cleanup, not compression optimism, makes this fit.
    state.used = HOSTED["windows"]["post_editor"] - LOCAL_RUSTUP_BYTES + cache
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("premature asset cache save", archive)
    state.used = HOSTED["windows"]["preflight"] - LOCAL_RUSTUP_BYTES + cache
    budget.check("asset cache save after workspace release", archive)


def test_prepared_compression_model_must_not_stand_in_for_a_final_export_measurement(metered_budget):
    state, budget = metered_budget
    # The 364MB value is the dependency-pruned RSCC estimate, not an actual
    # fresh catalog. Test the reserve with the installed-tree value supplied
    # at runtime; no estimated compression ratio may replace this amount.
    # Prior Windows final PCK metadata, used as a conservative existing-pack
    # fixture. It does not predict the size of a new intermediate first PCK.
    existing_pack = 2_100_196_680
    measured_prepared = 1_139_514_441
    projected_prepared = 364_044_245
    overhead = 67_108_864
    allocation = existing_pack + measured_prepared + overhead
    state.used = USABLE - (existing_pack + projected_prepared + overhead)
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("actual installed prepared tree before export", allocation)
    state.used = USABLE - allocation
    budget.check("final export after intermediate PCK retirement", allocation)


def test_conditional_late_component_forecast_requires_both_prepared_copies_to_shrink(metered_budget):
    state, budget = metered_budget
    # Conditional model, not a measured hosted late peak. All components except
    # the explicitly projected new native closure are measured witnesses. The
    # project and installed cooked payload are linked, but the final PCK is a
    # distinct copy. Crediting the compression saving only once misses that.
    current_native = 1_136_381_806
    projected_native = 364_044_245
    saving_per_copy = current_native - projected_native
    raw_component_forecast = (HOSTED["windows"]["post_editor"] - LOCAL_RUSTUP_BYTES
        - MAP_RETIREMENT_BYTES + 909_675_853 + LOCAL_VRAM_BYTES
        + 1_139_514_441 + 2_100_196_680)
    assert raw_component_forecast == 12_780_984_684
    state.used = raw_component_forecast
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("raw prepared payload plus streamed archive", client_release.PART_BYTES)
    state.used -= saving_per_copy
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("only one prepared copy reduced", client_release.PART_BYTES)
    state.used -= saving_per_copy
    budget.check("projected both prepared copies reduced", client_release.PART_BYTES)
    remaining = USABLE - state.used - client_release.PART_BYTES
    assert remaining == 495_254_982
    # Unmodelled allocations consume this headroom; they are not free merely
    # because native compression and guarded retirement succeeded.
    state.used += remaining + 1
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("late metadata or helper delta exceeded headroom", client_release.PART_BYTES)


def test_online_installer_forecast_can_exceed_archive_peak_after_extra_helpers(metered_budget):
    state, budget = metered_budget
    projected_components = 11_236_309_562
    measured_game_executable = 109_243_904
    # The local standalone has no updater. Its additional binary is only a
    # lower-bound sizing fixture here (embedded updater PCK adds more bytes);
    # its uninstall/cache hardlinks must not be charged as more full binaries.
    state.used = projected_components + 2 * measured_game_executable
    budget.check("late streamed archive", client_release.PART_BYTES)
    budget.check("before online installer", 536_870_912)
    assert USABLE - state.used - 536_870_912 == 8_331_718
    state.used += 8_331_719
    # A plan that tested only the smaller part reservation misses this phase.
    budget.check("archive still fits", client_release.PART_BYTES)
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("installer plus unmodelled native/helper metadata", 536_870_912)


def test_actual_fresh_tree_retirement_restores_conditional_installer_headroom(metered_budget):
    state, budget = metered_budget
    previous_tree = 1_139_514_441
    actual_fresh_native = 364_044_388
    actual_fresh_tree = 369_855_321
    assert actual_fresh_tree > actual_fresh_native
    # New 48-entry source-tree bytes are actual. The PCK tree-delta and helper
    # size remain explicit conditional inputs until the new final pack exists.
    # Both generation and installed source are hardlinked: retire their union
    # once, after qualification, rather than crediting two physical deletions.
    state.used = (12_780_984_684 - 2 * (previous_tree - actual_fresh_tree)
                  - actual_fresh_tree + 2 * 109_243_904)
    budget.check("installer after qualified cooked-source retirement", 536_870_912)
    remaining = USABLE - state.used - 536_870_912
    assert remaining == 372_830_157
    state.used += remaining + 1
    with pytest.raises(ValueError, match="disk budget exceeded"):
        budget.check("actual final pack/helper delta exhausted remaining capacity", 536_870_912)
