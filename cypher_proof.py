from falkordb import FalkorDB
try:
    db = FalkorDB(host='localhost', port=6380)
    g = db.select_graph('graphiti')
    print("Connected to FalkorDB on port 6380.")
    
    # Insert dummy edge
    g.query("CREATE (n:Entity {uuid: 'test-n1', name: 'TestNode1'})-[e:RELATES_TO {fact: 'FalkorDB connectivity confirmed!'}]->(m:Entity {uuid: 'test-n2', name: 'TestNode2'})")
    
    # Read it back
    res = g.query("MATCH (n:Entity {uuid: 'test-n1'})-[e:RELATES_TO]->(m:Entity {uuid: 'test-n2'}) RETURN n.name, e.fact, m.name")
    
    print("\n[Connectivity Confirmed] Cypher Query Results:")
    for record in res.result_set:
        print(f"- Node1: {record[0]}, Fact: '{record[1]}', Node2: {record[2]}")
        
    # Cleanup
    g.query("MATCH (n:Entity {uuid: 'test-n1'}) DETACH DELETE n")
    g.query("MATCH (n:Entity {uuid: 'test-n2'}) DETACH DELETE n")
    print("\nCleanup complete.")
except Exception as e:
    print(f"Error: {e}")
