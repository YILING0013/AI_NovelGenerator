from novel_generator.pipeline import PipelineFactory


def test_create_default_pipeline_wires_required_components():
    config = {
        "project_path": ".",
        "interface_format": "openai",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-5",
        "num_chapters": 10,
        "word_number": 3000,
    }

    pipeline = PipelineFactory.create_default_pipeline(config)

    assert pipeline.data_loader is not None
    assert pipeline.data_saver is not None
    assert pipeline.event_handler is not None
    assert len(pipeline.stages) == 4
    assert [stage.name for stage in pipeline.stages] == [
        "BlueprintGeneration",
        "PromptBuilding",
        "ChapterGeneration",
        "Finalization",
    ]
