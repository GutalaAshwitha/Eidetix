from memory.pipeline import MemoryPipeline
pipeline = MemoryPipeline()
res = pipeline.answer_question('What car did the user previously own?')
print('PREV:', res)
