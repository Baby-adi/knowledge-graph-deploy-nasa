import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import json
import re
import os

# --- Streamlit page setup ---
st.set_page_config(page_title="NASA Publications 3D Knowledge Graph", layout="wide")
st.title("s")

# --- Data Loading and Caching ---
@st.cache_data
def load_graph_data():
    """Loads data from JSON and builds the full knowledge graph."""
    try:
        with open('sb_publication_output.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        st.error("Error: `sb_publication_output.json` not found.")
        return nx.Graph()
    
    G = nx.Graph()
    type_colors = {
        'Publication': '#ff6f61', 'Mission': '#9e9ac8', 'Keyword': '#74c476',
        'Organism': '#6baed6', 'Location': '#fdae6b'
    }
    
    # Parse each document in the JSON
    for doc_id, doc in data.items():
        if not isinstance(doc, dict):
            continue
            
        title = doc.get('Title', '')
        if not title or len(title) < 5:
            continue
        
        # Add publication node
        pub_id = f"pub_{doc_id}"
        G.add_node(pub_id, type='Publication', color=type_colors['Publication'], 
                   size=18, label=title[:100])
        
        # Extract missions from Introduction text (e.g., "Bion-M 1", "STS-131", "ISS")
        intro = doc.get('Introduction', '') or ''
        if intro:
            mission_pattern = re.compile(r'\b(Bion-M\s?\d+|STS-\d+|ISS|International Space Station|Space Shuttle|Spacelab-?\d*|NeuroLab)\b', re.IGNORECASE)
            missions = set(mission_pattern.findall(intro))
            for mission in missions:
                mission_clean = mission.strip()
                G.add_node(mission_clean, type='Mission', color=type_colors['Mission'], 
                          size=14, label=mission_clean)
                G.add_edge(pub_id, mission_clean)
        
        # Extract keywords from title and abstract
        abstract = doc.get('Abstract', '') or ''
        combined_text = f"{title} {abstract}".lower()
        
        # Common space biology keywords
        keywords = {
            'microgravity': 'Microgravity',
            'bone': 'Bone',
            'muscle': 'Muscle',
            'cardiovascular': 'Cardiovascular',
            'radiation': 'Radiation',
            'oxidative stress': 'Oxidative Stress',
            'cell cycle': 'Cell Cycle',
            'stem cell': 'Stem Cells',
            'osteoblast': 'Osteoblasts',
            'spaceflight': 'Spaceflight',
            'immune': 'Immune System',
            'gene expression': 'Gene Expression'
        }
        
        for keyword_search, keyword_label in keywords.items():
            if keyword_search in combined_text:
                G.add_node(keyword_label, type='Keyword', color=type_colors['Keyword'], 
                          size=10, label=keyword_label)
                G.add_edge(pub_id, keyword_label)
        
        # Extract organisms (mice, rats, humans)
        organism_pattern = re.compile(r'\b(mice|mouse|Mus musculus|rats|human|Homo sapiens|C57BL/6J?)\b', re.IGNORECASE)
        organisms = set(organism_pattern.findall(intro + ' ' + abstract))
        organism_mapping = {
            'mice': 'Mice', 'mouse': 'Mice', 'mus musculus': 'Mice',
            'rats': 'Rats', 'human': 'Humans', 'homo sapiens': 'Humans',
            'c57bl/6j': 'Mice', 'c57bl/6': 'Mice'
        }
        
        for org in organisms:
            org_label = organism_mapping.get(org.lower(), org.title())
            G.add_node(org_label, type='Organism', color=type_colors['Organism'], 
                      size=12, label=org_label)
            G.add_edge(pub_id, org_label)
    
    return G

# Load the full graph
full_G = load_graph_data()

# Display graph statistics
st.sidebar.header("Graph Statistics")
st.sidebar.write(f"Total Nodes: {full_G.number_of_nodes()}")
st.sidebar.write(f"Total Edges: {full_G.number_of_edges()}")

# --- Streamlit Sidebar Controls ---
st.sidebar.header("Graph Controls")
# Dynamically set slider bounds based on number of publication nodes in the full graph
total_publications = len([n for n, d in full_G.nodes(data=True) if d.get('type') == 'Publication'])
# Provide sensible fallbacks
slider_min = 1 if total_publications >= 1 else 0
slider_max = total_publications if total_publications >= 1 else 1
# Keep a familiar default (50) but clamp to available range
default_val = 50 if total_publications >= 50 else slider_max
max_pubs = st.sidebar.slider("Max Publications to Display", slider_min, slider_max, default_val)

all_node_types = sorted(list(set(nx.get_node_attributes(full_G, 'type').values())))
desired_defaults = ['Publication', 'Mission', 'Keyword', 'Organism']
actual_defaults = [t for t in desired_defaults if t in all_node_types]

selected_types = st.sidebar.multiselect(
    "Select Node Types to Display",
    options=all_node_types,
    default=actual_defaults
)

# 1. Get all publication nodes (no slice) so the subgraph includes every publication
pub_nodes_all = [n for n, d in full_G.nodes(data=True) if d.get('type') == 'Publication']

# 2. Create a subgraph containing all publications and their direct neighbors
nodes_to_consider = set(pub_nodes_all)
for pub_node in pub_nodes_all:
    nodes_to_consider.update(full_G.neighbors(pub_node))
sub_G = full_G.subgraph(nodes_to_consider)

# 3. From this subgraph, select only the nodes whose type is in the multiselect widget
# But when publications are selected, limit which publication nodes are shown to the
# first `max_pubs` (to preserve the slider behavior while still building on full data).
pubs_in_sub = [n for n, d in sub_G.nodes(data=True) if d.get('type') == 'Publication']
pubs_to_show = set(pubs_in_sub[:max_pubs]) if 'Publication' in selected_types else set()

final_nodes_to_keep = []
for n, d in sub_G.nodes(data=True):
    node_type = d.get('type')
    if node_type not in selected_types:
        continue
    if node_type == 'Publication':
        # Only include publication nodes that fall within the slider limit
        if n in pubs_to_show:
            final_nodes_to_keep.append(n)
    else:
        # include non-publication nodes if their type is selected
        final_nodes_to_keep.append(n)

final_G = sub_G.subgraph(final_nodes_to_keep)


# --- Generate 3D Layout ---
if len(final_G.nodes()) > 0:
    pos = nx.spring_layout(final_G, dim=3, seed=42, iterations=50)

    # --- Create Plotly Traces ---
    edge_x, edge_y, edge_z = [], [], []
    edge_labels=[]
    for edge in final_G.edges():
        x0, y0, z0 = pos[edge[0]]
        x1, y1, z1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        edge_z.extend([z0, z1, None])
    
        # Get node types for meaningful hover text
        src_type = final_G.nodes[edge[0]].get('type', 'Unknown')
        dst_type = final_G.nodes[edge[1]].get('type', 'Unknown')
        edge_labels.append(f"{edge[0]} → {edge[1]}<br>({src_type} → {dst_type})")

    edge_trace = go.Scatter3d(
        x=edge_x, y=edge_y, z=edge_z,
        line=dict(width=1, color='#999'),
        text=edge_labels * 2,
        hoverinfo='text',
        mode='lines'
    )

    node_x, node_y, node_z = [], [], []
    node_colors, node_sizes, node_labels = [], [], []
    node_degrees = []
    for node, attrs in final_G.nodes(data=True):
        x, y, z = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_z.append(z)
        node_colors.append(attrs.get('color', '#cccccc'))
        node_sizes.append(attrs.get('size', 10))
        node_labels.append(f"{attrs.get('type', 'N/A')}:<br>{attrs.get('label', 'N/A')}")
        node_degrees.append(final_G.degree(node))

    node_trace = go.Scatter3d(
        x=node_x, y=node_y, z=node_z,
        mode='markers',
        hoverinfo='text',
        text=node_labels,
        marker=dict(
            showscale=True,
            colorscale='Viridis',
            color=node_degrees,
            size=node_sizes,
            colorbar=dict(
                thickness=15,
                title=dict(text='Node Connections', side='right'),
                xanchor='left'
            ),
            line_width=1
        )
    )

    # --- Combine traces and create figure ---
    fig = go.Figure(data=[edge_trace, node_trace],
        layout=go.Layout(
            title='3D Knowledge Graph of NASA Publications',
            showlegend=False,
            margin=dict(l=0, r=0, b=0, t=40),
            scene=dict(
                xaxis=dict(showbackground=False, visible=False),
                yaxis=dict(showbackground=False, visible=False),
                zaxis=dict(showbackground=False, visible=False)
            )
        )
    )
    fig.update_layout(height=800)
    # --- Display in Streamlit ---
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No data to display. Check your selections in the sidebar.")