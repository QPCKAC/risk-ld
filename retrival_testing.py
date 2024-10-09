import os
import streamlit as st
from langchain_pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
import base64
import fitz  # PyMuPDF
from pinecone import Pinecone as PineconeClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define directories
current_dir = os.path.dirname(os.path.abspath(__file__))

# Initialize OpenAI embeddings
@st.cache_resource
def get_embeddings():
    try:
        embeddings = OpenAIEmbeddings()
        # Test the embeddings
        test_embedding = embeddings.embed_query("Test sentence")
        #st.sidebar.success(f"OpenAI embeddings initialized successfully. Dimension: {len(test_embedding)}")
        return embeddings
    except Exception as e:
        #st.sidebar.error(f"Failed to initialize OpenAI embeddings: {e}")
        return None

embeddings = get_embeddings()

# Initialize Pinecone
@st.cache_resource
def init_pinecone():
    try:
        pc = PineconeClient(api_key=os.getenv("PINECONE_API_KEY"))
        index_name = os.getenv("PINECONE_INDEX_NAME", "risk")
        st.sidebar.success(f"Connected to Pinecone. Index: {index_name}")
        return pc, index_name
    except Exception as e:
        st.sidebar.error(f"Failed to connect to Pinecone: {e}")
        return None, None

pc, index_name = init_pinecone()

# Load the existing Pinecone database
@st.cache_resource
def load_vectordb():
    if embeddings and pc and index_name:
        try:
            vectorstore = Pinecone(index_name=index_name, embedding=embeddings)
            st.sidebar.success("Vectorstore loaded successfully")
            return vectorstore
        except Exception as e:
            st.sidebar.error(f"Failed to load vectorstore: {e}")
    else:
        st.sidebar.error("Cannot load vectorstore: Embeddings or Pinecone not initialized")
    return None

vectorstore = load_vectordb()

def split_text(text, max_length=100):
    words = text.split()
    chunks = []
    current_chunk = ''
    for word in words:
        if len(current_chunk) + len(word) + 1 <= max_length:
            current_chunk += ' ' + word if current_chunk else word
        else:
            chunks.append(current_chunk)
            current_chunk = word
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

# Generate PDF link function
def generate_pdf_link(metadata):
    pdf_dir = os.path.join(current_dir, "data")
    pdf_path = os.path.join(pdf_dir, metadata['source'])
    return pdf_path, metadata['page']

# Display PDF function with highlighting
def display_pdf(pdf_path, page=None, highlight_text=None):
    try:
        with fitz.open(pdf_path) as doc:
            if page is None:
                page = 1
            page_obj = doc.load_page(page - 1)

            if highlight_text:
                chunks = split_text(highlight_text, max_length=1000)
                for chunk in chunks:
                    areas = page_obj.search_for(chunk)
                    for area in areas:
                        page_obj.add_highlight_annot(area)

            pix = page_obj.get_pixmap(dpi=120)
            img_bytes = pix.tobytes()
            st.image(img_bytes, caption=f"Page {page}", use_column_width=True)

    except Exception as e:
        st.error(f"Error displaying PDF: {e}")

# # Highlight PDF function
# def highlight_pdf(pdf_path, page, highlight_text):
#     try:
#         doc = fitz.open(pdf_path)
#         page_obj = doc.load_page(page - 1)
#         chunks = split_text(highlight_text, max_length=100)
#         for chunk in chunks:
#             text_instances = page_obj.search_for(chunk)
#             for inst in text_instances:
#                 highlight = page_obj.add_highlight_annot(inst)
        
#         pix = page_obj.get_pixmap()
#         img_bytes = pix.tobytes()
#         img_base64 = base64.b64encode(img_bytes).decode()
        
#         highlighted_page = f"""
#         <div id="highlighted-page" style="height:600px; overflow-y:scroll;">
#             <img src="data:image/png;base64,{img_base64}" style="width:100%;"/>
#         </div>
#         """
#         st.components.v1.html(highlighted_page, height=620, scrolling=True)
#         doc.close()
#     except Exception as e:
#         st.error(f"Error highlighting PDF: {e}")

# Show PDF function (updated)
def show_pdf(pdf_path, page, highlight_text=None):
    st.session_state.pdf_viewer = {
        "pdf_path": pdf_path,
        "page": page,
        "highlight_text": highlight_text
    }

# Create a retriever
@st.cache_resource
def get_retriever():
    if vectorstore:
        return vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 3
            }
        )
    return None

retriever = get_retriever()

# Streamlit UI
st.title("ACOG Document Retrieval System")

# Initialize session state variables
if 'pdf_viewer' not in st.session_state:
    st.session_state.pdf_viewer = None
if 'docs' not in st.session_state:
    st.session_state.docs = None
if 'docs_and_scores' not in st.session_state:
    st.session_state.docs_and_scores = None

# User input
query = st.text_input("Enter your question about ACOG guidelines:")

if query and (query != st.session_state.get('last_query', '')):
    st.session_state.last_query = query
    if vectorstore:
        try:
            st.session_state.docs_and_scores = vectorstore.similarity_search_with_score(query, k=3)
        except Exception as e:
            st.error(f"Error retrieving documents: {e}")
    else:
        st.error("Vectorstore is not initialized. Please check the sidebar for initialization errors.")

if st.session_state.docs_and_scores:
    st.markdown("### Retrieved Chunks:")
    for i, (doc, score) in enumerate(st.session_state.docs_and_scores):
        with st.expander(f"Chunk {i+1}: {doc.metadata.get('source', 'Unknown')} (Score: {score:.4f})"):
            st.write("Content:")
            st.write(doc.page_content)
            st.write(f"Similarity Score: {score:.4f}")
            st.write(f"Source: {doc.metadata.get('source', 'Unknown')}")
            st.write(f"Page: {doc.metadata.get('page', 'Unknown')}")
            pdf_path, page = generate_pdf_link(doc.metadata)
            if st.button(f"View PDF (Page {page})", key=f"pdf_button_{i}"):
                show_pdf(pdf_path, page, doc.page_content)
    # Display PDF if requested
    if st.session_state.pdf_viewer:
        st.markdown("### PDF Viewer")
        display_pdf(
            st.session_state.pdf_viewer["pdf_path"],
            st.session_state.pdf_viewer["page"],
            st.session_state.pdf_viewer["highlight_text"]
        )

# Add a sidebar with some information
st.sidebar.title("About")
st.sidebar.info("This app retrieves relevant chunks from ACOG guidelines using a Pinecone database.")

# Debug information
st.sidebar.title("Debug Info")
st.sidebar.write(f"Query: {st.session_state.get('last_query', 'No query yet')}")
st.sidebar.write(f"Number of docs retrieved: {len(st.session_state.docs) if st.session_state.docs else 0}")
st.sidebar.write(f"Pinecone index: {index_name}")