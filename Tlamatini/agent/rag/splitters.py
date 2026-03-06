from langchain_text_splitters import RecursiveCharacterTextSplitter

def get_text_splitter(chunk_size: int = 500, chunk_overlap: int = 100) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
