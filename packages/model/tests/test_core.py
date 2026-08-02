from model import HomageCoreConfig, HomageCoreModel


def test_model_shape_and_parameter_estimate():
    model = HomageCoreModel(HomageCoreConfig())
    assert model.forward_shape(2, 16) == (2, 16, 256)
    assert model.summary()["estimated_parameters"] > 1_000_000
