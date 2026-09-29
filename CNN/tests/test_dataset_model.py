import numpy as np
import torch
from lens_soiling import CLASSES, TILE
from lens_soiling.dataset import SyntheticTiles, tile_frame, to_tensor
from lens_soiling.model import LensSoilNet, count_params, count_macs


def test_dataset_item_and_determinism():
    ds = SyntheticTiles(None, 20, seed=5)
    x, y = ds[3]
    assert x.shape == (3, TILE, TILE) and x.dtype == torch.float32
    assert -1.0 <= x.min() and x.max() <= 1.0
    assert 0 <= y < len(CLASSES)
    x2, y2 = SyntheticTiles(None, 20, seed=5)[3]
    assert torch.equal(x, x2) and y == y2


def test_dataset_has_all_classes():
    ds = SyntheticTiles(None, 60, seed=7, augment=False)
    labels = {ds[i][1] for i in range(60)}
    assert labels == {0, 1, 2}


def test_model_shapes_and_budget():
    m = LensSoilNet()
    out = m(torch.zeros(4, 3, TILE, TILE))
    assert out.shape == (4, len(CLASSES))
    assert count_params(m) < 120_000, "must fit MCU flash after int8"
    assert count_macs(m) < 6_000_000, "keep per-tile MACs small for a Cortex-M7"


def test_tile_frame_grid():
    frame = (np.random.default_rng(0).random((200, 330, 3)) * 255).astype(np.uint8)
    batch, (r, c) = tile_frame(frame)
    assert (r, c) == (3, 5) and batch.shape == (15, 3, TILE, TILE)
    # first tile equals top-left crop
    assert torch.allclose(batch[0], to_tensor(frame[:TILE, :TILE]))
