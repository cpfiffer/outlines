import pytest
import torch
import numpy as np
import pandas as pd
from typing import List

from outlines.processors.tracking import LogitTracker, track_logits
from outlines.processors.base_logits_processor import OutlinesLogitsProcessor


class MockProcessor(OutlinesLogitsProcessor):
    """Mock processor that modifies logits in a predictable way."""

    def __init__(self):
        self.tokenizer = MockTokenizer()

    def process_logits(
        self, input_ids: List[List[int]], logits: torch.Tensor
    ) -> torch.Tensor:
        # For testing purposes, set every other logit to -inf
        processed = logits.clone()
        processed[:, ::2] = float("-inf")
        return processed


class MockTokenizer:
    """Mock tokenizer for testing."""

    def decode(self, token_ids):
        if not token_ids:  # Handle empty list case
            return ""
        # Concatenate all tokens
        return "".join(f"token_{tid}" for tid in token_ids)


@pytest.fixture
def processor():
    """Fixture for creating a tracking processor with a mock base processor."""
    base = MockProcessor()
    processor = LogitTracker(base)
    processor.tokenizer = base.tokenizer  # Ensure tokenizer is available
    return processor


def test_initialization():
    """Test initialization with various parameters."""
    base = MockProcessor()

    # Basic initialization
    processor = LogitTracker(base)
    assert processor.processor == base
    assert len(processor.unstructured_logits) == 0
    assert len(processor.structured_logits) == 0
    assert processor.vocab_tokens is None
    assert len(processor.chosen_tokens) == 0
    assert not processor._started

    # Without processor
    processor = LogitTracker(None)
    assert processor.processor is None


@pytest.mark.parametrize("vocab_size", [10, 100])
def test_logit_processing(processor, vocab_size):
    """Test logit processing with different vocab sizes."""
    input_ids = [[0]]  # Single batch
    logits = torch.ones(1, vocab_size)  # Single batch

    processed = processor.process_logits(input_ids, logits)

    # Check tracking
    assert len(processor.unstructured_logits) == 1
    assert len(processor.structured_logits) == 1
    assert processor.unstructured_logits[0].shape == (vocab_size,)
    assert processor.structured_logits[0].shape == (vocab_size,)

    # Check original logits preserved
    assert torch.allclose(torch.tensor(processor.unstructured_logits[0]), logits[0])

    # Check processing (every other logit should be -inf)
    assert torch.all(torch.isinf(processed[:, ::2]))
    assert not torch.any(torch.isinf(processed[:, 1::2]))

    # Check chosen token tracking
    assert processor._started
    assert len(processor.chosen_tokens) == 0  # First call doesn't add token


def test_batch_size_validation(processor):
    """Test that multi-batch processing raises an error."""
    # Test with multiple sequences in input_ids
    with pytest.raises(ValueError, match="only supports single-batch processing"):
        processor.process_logits([[0], [0]], torch.ones(2, 10))

    # Test with multiple batches in logits
    with pytest.raises(ValueError, match="only supports single-batch processing"):
        processor.process_logits([[0]], torch.ones(2, 10))


def test_chosen_token_tracking(processor):
    """Test tracking of chosen tokens during generation."""
    # First token
    processor.process_logits([[0]], torch.ones(1, 10))
    assert len(processor.chosen_tokens) == 0
    assert processor._started

    # Second token - should track the previous choice
    processor.process_logits([[0, 1]], torch.ones(1, 10))
    assert len(processor.chosen_tokens) == 1
    assert processor.chosen_tokens[0] == 1

    # Third token
    processor.process_logits([[0, 1, 2]], torch.ones(1, 10))
    assert len(processor.chosen_tokens) == 2
    assert processor.chosen_tokens[1] == 2


def test_get_probabilities(processor):
    """Test probability distribution computation."""
    # Process a few positions
    for i in range(3):
        # Create logits that will result in valid probability distributions
        logits = torch.full((1, 10), -100.0)  # Very negative but not -inf
        logits[0, i] = 0.0  # Make one token dominate the probability mass
        print(f"\nPosition {i} logits:")
        print(f"Raw logits: {logits[0]}")
        processor.process_logits([[j for j in range(i + 1)]], logits)

        # Print the softmax of these logits to debug
        probs = torch.softmax(logits[0], dim=-1)
        print(f"Raw probabilities: {probs}")
        print(f"Probability sum: {probs.sum()}")

    probs = processor.get_probabilities()
    print("\nProbabilities:")
    print(f"Unstructured shape: {probs['unstructured'].shape}")

    # For matrix form, we need to check each position (column) separately
    for pos in range(probs["unstructured"].shape[1]):
        dist = probs["unstructured"][:, pos]
        print(f"Position {pos} sum: {np.sum(dist)}")
        print(f"Position {pos} distribution: {dist}")
        assert np.allclose(np.sum(dist), 1.0, rtol=1e-5)

        # Check structured probabilities
        dist = probs["structured"][:, pos]
        valid_probs = dist[~np.isinf(dist)]
        if len(valid_probs) > 0:
            assert np.allclose(np.sum(valid_probs), 1.0, rtol=1e-5)


def test_get_logits(processor):
    """Test logit value retrieval."""
    # Process a few positions with known values
    for i in range(3):
        logits = torch.full((1, 10), float(i))
        processor.process_logits([[j for j in range(i + 1)]], logits)

    logits = processor.get_logits()

    assert set(logits.keys()) == {"unstructured", "structured"}

    assert isinstance(logits["unstructured"], np.ndarray)
    assert logits["unstructured"].shape == (10, 3)
    assert logits["structured"].shape == (10, 3)
    # Check values match what we put in
    for i in range(3):
        assert np.allclose(logits["unstructured"][:, i], i)


def test_get_top_tokens(processor):
    """Test top token retrieval with various parameters."""
    # Process some logits with known values
    logits = torch.tensor([[2.0, -1.0, 1.0, 0.0, 3.0]])
    processor.process_logits([[0]], logits)

    # Test with different k values and explicitly disable logits
    results = processor.get_top_tokens(k=2, include_logits=False)
    assert len(results) == 1  # One position
    assert len(results[0]["tokens"]) == 2  # k=2 tokens

    # Check token info structure
    token_info = results[0]["tokens"][0]
    assert set(token_info.keys()) == {
        "token",
        "unstructured_prob",
        "structured_prob",
        "is_chosen",
    }

    # Test position filtering
    results = processor.get_top_tokens(positions=[0])
    assert len(results) == 1

    # Test invalid position
    results = processor.get_top_tokens(positions=[100])
    assert len(results) == 0


def test_sequence_reconstruction(processor):
    """Test sequence reconstruction from chosen tokens."""
    # Process a sequence
    tokens = [[0], [0, 1], [0, 1, 2]]
    for ids in tokens:
        print(f"\nProcessing tokens: {ids}")
        processor.process_logits([ids], torch.ones(1, 10))

    print(f"\nFinal chosen_tokens: {processor.chosen_tokens}")
    print(f"sequence(0): '{processor.sequence_up_to(0)}'")
    print(f"sequence(1): '{processor.sequence_up_to(1)}'")
    print(f"sequence(2): '{processor.sequence_up_to(2)}'")

    # Test different positions
    assert processor.sequence_up_to(0) == ""  # No tokens yet
    assert processor.sequence_up_to(1) == "token_1"  # First token
    assert processor.sequence_up_to(2) == "token_1token_2"  # Two tokens
    assert processor.sequence_up_to() == "token_1token_2"  # Full sequence

    # Test position beyond current sequence
    assert processor.sequence_up_to(100) == "token_1token_2"


def test_to_dataframe(processor):
    """Test DataFrame conversion with various parameters."""
    # Skip if pandas not available
    pytest.importorskip("pandas")

    # Process some logits
    logits = torch.tensor([[2.0, -1.0, 1.0, 0.0, 3.0]])
    processor.process_logits([[0]], logits)

    # Test probabilities
    df = processor.get_probabilities_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"position", "token", "natural", "constrained", "chosen"}
    assert df["position"].nunique() == 1
    assert (df["natural"] >= 0).all() and (df["natural"] <= 1).all()

    # Test logits
    df = processor.get_logits_dataframe()
    assert not (
        (df["natural"] >= 0) & (df["natural"] <= 1)
    ).all()  # Logits can be any value

    # Test min_value filter
    df = processor.get_probabilities_dataframe(min_value=0.1)
    assert len(df) > 0
    assert ((df["natural"].abs() >= 0.1) | (df["constrained"].abs() >= 0.1)).all()


def test_clear(processor):
    """Test clearing tracked data."""
    # Add some data
    processor.process_logits([[0]], torch.ones(1, 10))
    processor.process_logits([[0, 1]], torch.ones(1, 10))

    assert len(processor.unstructured_logits) > 0
    assert len(processor.structured_logits) > 0
    assert len(processor.chosen_tokens) > 0
    assert processor._started  # Should be True after processing

    # Clear
    processor.clear()

    assert len(processor.unstructured_logits) == 0
    assert len(processor.structured_logits) == 0
    assert len(processor.chosen_tokens) == 0
    assert processor._started  # Should remain True after clear


def test_track_logits_helper():
    """Test the track_logits convenience function."""

    class MockGenerator:
        def __init__(self):
            self.logits_processor = MockProcessor()

    generator = MockGenerator()
    tracked = track_logits(generator)

    assert isinstance(tracked.logits_processor, LogitTracker)
    assert isinstance(tracked.logits_processor.processor, MockProcessor)


@pytest.mark.parametrize(
    "invalid_value",
    [
        "not a processor",  # Invalid processor type
        None,  # No processor
    ],
)
def test_invalid_inputs(invalid_value):
    """Test handling of invalid inputs."""
    if isinstance(invalid_value, str):
        processor = LogitTracker(invalid_value)
        with pytest.raises(AttributeError):
            processor.process_logits([[0]], torch.ones(1, 10))
    else:
        # None processor should work but not modify logits
        processor = LogitTracker(invalid_value)
        logits = torch.ones(1, 10)
        result = processor.process_logits([[0]], logits)
        assert torch.allclose(result, logits)


def test_missing_tokenizer():
    """Test behavior when processor has no tokenizer."""

    class ProcessorWithoutTokenizer(OutlinesLogitsProcessor):
        def process_logits(self, input_ids, logits):
            return logits

    processor = LogitTracker(ProcessorWithoutTokenizer())
    processor.process_logits([[0]], torch.ones(1, 10))

    with pytest.raises(AttributeError):
        processor.get_vocab_mapping()


def test_shape_mismatch():
    """Test error handling for shape mismatch between input_ids and logits."""
    processor = LogitTracker(MockProcessor())

    # Test batch size mismatch
    input_ids = [[0]]  # batch_size=1
    logits = torch.ones(2, 10)  # batch_size=2

    print("\nShape mismatch test:")
    print(f"input_ids shape: {len(input_ids)}x{len(input_ids[0])}")
    print(f"logits shape: {logits.shape}")
    print(f"logits[0]: {logits[0]}")  # Print first batch
    print(f"logits: {logits}")  # Print full tensor

    # We need to ensure the processor validates batch sizes
    # This should fail because logits has batch_size=2 but input_ids has batch_size=1
    with pytest.raises(ValueError, match=r"only supports single-batch processing"):
        processor.process_logits(input_ids, logits)
