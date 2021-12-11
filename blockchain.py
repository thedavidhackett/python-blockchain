import hashlib
import json
import requests
from textwrap import dedent
from time import time
from typing import Any, Dict, List, Set
from urllib.parse import ParseResult, urlparse
from uuid import uuid4

from flask import Flask, jsonify, request


class Blockchain(object):
    """A blockchain implemented in python
    """
    def __init__(self) -> None:
        self.chain : List = []
        self.current_transactions : List = []
        self.nodes : Set = set()

        self.new_block(1, 100)

    def new_block(self, proof : int, previous_hash : str = None) -> Dict:
        """Creates a new Block in the Blockchain

        Parameters
        ---------
        proof : int
            The proof given by the Proof of Work algorithm
        previous_hash : str, default=None
            Hash of the previous Block

        Returns:
        --------
        Dict
            New Block
        """
        block = {
            "index" : len(self.chain) + 1,
            "timestamp": time(),
            "transactions": self.current_transactions,
            "proof": proof,
            "previous_hash": previous_hash or self.hash(self.chain[-1]),
        }

        self.current_transactions = []

        self.chain.append(block)
        return block


    def new_transaction(self, sender : str, recipient : str, amount : int) -> int:
        """Creates a new transaction to go into the next minded Block

        Parameters
        ----------
        sender : str
            Address of the Sender
        recipient : str
            Address of the recipient
        amount : int
            The amount

        Returns
        -------
        int
            The index of the block that will hold this transaction
        """
        self.current_transactions.append({
            "sender": sender,
            "recipient": recipient,
            "amount": amount
        })

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block) -> str:
        """Creates a SHA-256 hash of a Block

        Parameters
        ----------
        block : Dict
            A block

        Returns
        -------
        str
            A hash
        """
        block_string : bytes = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self) -> Dict:
        """The last block in the chain
        """
        return self.chain[-1]

    def proof_of_work(self, last_proof : int) -> int:
        """Simple Proof of Work Algorithm:
            - Find a number p' such that hash(pp') contains 3 leading zeroes
              where p is the previous p'
            - p is the previous proof, and p' is the new proof

        Parameters
        ----------
        last_proof : int
            The previous proof

        Returns
        -------
        int
            The new proof
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """Validates the proof if proof contains 4 leading zeroes

        Parameters
        ----------
        last_proof : int
            The previous proof
        proof : int
            The current proof

        Returns
        -------
        bool
            True is proof is valid, false otherwise
        """

        guess : bytes = f'{last_proof}{proof}'.encode()
        guess_hash : str =  hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def register_node(self, address : str) -> None:
        """Add a new node to the list of nodes

        Parameters
        ----------
        address : str
            Address of the node. Eg. 'http://192/.168.0.5:5000'
        """

        parsed_url : ParseResult = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain : List) -> bool:
        """Determine if a given blockchain is valid

        Parameters
        ----------
        chain : List
            A block chain

        Returns
        -------
        bool
            True if valid, False otherwise
        """

        last_block : Dict = chain[0]
        current_index : int = 1

        while current_index < len(chain):
            block : Dict = chain[current_index]
            print(f'{last_block}')
            print("\n-------------------\n")

            if block['previous_hash'] != self.hash(last_block):
                return False

            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block : Dict = block

            current_index += 1

        return True

    def resolve_conflicts(self):
        """Consensus algorithm

        This consensus algorithm resolves conflicts by replacing the chain with
        longest one in the network.

        Returns
        -------
        bool
            True if chain was replaced, False otherwise
        """

        neighbors : List = self.nodes
        new_chain : Any = None

        max_length : int = len(self.chain)

        for node in neighbors:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length : int = response.json()['length']
                chain : List = response.json()['chain']

                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            return True

        return False


app = Flask(__name__)

node_identifier : str = str(uuid4()).replace('-', '')

blockchain : Blockchain = Blockchain()

@app.route('/mine', methods=["GET"])
def mine():
    last_block : Dict = blockchain.last_block
    last_proof : int = last_block['proof']
    proof : int = blockchain.proof_of_work(last_proof)
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1
    )

    previous_hash : str = blockchain.hash(last_block)
    block : Dict = blockchain.new_block(proof, previous_hash)

    response : Dict = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash']
    }
    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values : List[str] = request.get_json()

    required : List = ['sender', 'recipient', 'amount']

    if not all(k in values for k in required):
        return 'Missing values', 400

    index : int = blockchain.new_transaction(values['sender'], \
        values['recipient'], values['amount'])

    response : Dict[str, str] = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }

    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values : Any = request.get_json()

    nodes : List = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': len(blockchain.nodes)
    }

    return jsonify(response), 201

@app.route('/nodes/resolve', methods=["GET"])
def consensus():
    replaced : bool = blockchain.resolve_conflicts()

    if replaced:
        response : Dict = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response : Dict = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    app.run(host='0.0.0.0', port=5001)
