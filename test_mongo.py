import pymongo
import sys

uri = "mongodb+srv://asta_admin:Meta%40astamangodb@asta-jarvis-cluster.a399efa.mongodb.net/?retryWrites=false&connectTimeoutMS=20000&socketTimeoutMS=30000&appName=Asta-Jarvis-Cluster"

try:
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    print(client.admin.command('ping'))
    print("Success")
except Exception as e:
    print("Error:", e)
    sys.exit(1)
