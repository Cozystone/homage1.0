from packages.splatra_turbovec.chunking import chunk_particles
from packages.splatra_turbovec.codec import compress_chunk, compression_stats, decompress_chunk, estimate_error
from packages.splatra_turbovec.proof import generate_orb_particles


def test_compress_decompress_preserves_count_and_bounds():
    chunk = chunk_particles(generate_orb_particles(1200), chunk_size=4.0)[0]
    compressed = compress_chunk(chunk, bits=12)
    restored = decompress_chunk(compressed)
    error = estimate_error(chunk, restored)
    stats = compression_stats(chunk, compressed)
    assert restored.particle_count == chunk.particle_count
    assert stats["compression_ratio"] > 1.0
    assert error["max_position_error"] < 0.004
    assert error["max_color_error"] <= 1 / 255 + 0.0001
    assert compressed.stats["turbovec_backend"] == "local_quantized_zlib_proof"
