import argparse
import os
import sys
import logging
from deepsearcher import configuration
from deepsearcher.configuration import init_rbase_config
from deepsearcher.api.rbase_util.sync.classify import load_classifier_value_by_vector_db
from deepsearcher.tools.log import set_dev_mode, set_level, debug

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description="Debug script for load_classifier_value_by_vector_db")
    parser.add_argument("classifier_id", type=int, help="The ID of the classifier")
    parser.add_argument("queries", nargs='+', help="One or more queries in format 'entity_query::entity_name'. If '::' is omitted, entity_name will be same as entity_query.")
    parser.add_argument("--top-k", type=int, default=10, help="Number of top results to retrieve (default: 10)")
    parser.add_argument("--confirm-score", type=float, default=0.5, help="Score threshold for confirmation (default: 0.5)")
    parser.add_argument("--valid-score", type=float, default=3, help="Score threshold for validity (default: 3)")
    parser.add_argument("--collection", type=str, default="classifier_value_entities", help="Vector DB collection name (default: classifier_value_entities)")
    parser.add_argument('--env', type=str, default='dev', help='Environment, default is dev')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose debug info')
    
    args = parser.parse_args()

    # Set log level
    if args.verbose:
        set_dev_mode(True)
        set_level(logging.DEBUG)
    else:
        set_level(logging.INFO)

    # 初始化配置
    init_rbase_config()

    # Concatenate environment prefix
    full_collection_name = f"{args.env}_{args.collection}"

    print(f"Starting search for classifier_id: {args.classifier_id}")
    print(f"Collection: {full_collection_name}")
    print(f"Parameters: top_k={args.top_k}, confirm_score={args.confirm_score}, valid_score={args.valid_score}")
    print("-" * 50)

    if not configuration.vector_db:
        print("Error: Vector DB not initialized.")
        return

    for input_arg in args.queries:
        # Parse input format: entity_query::entity_name
        if "::" in input_arg:
            entity_query, entity_name = input_arg.split("::", 1)
            entity_query = entity_query.strip()
            entity_name = entity_name.strip()
        else:
            entity_query = input_arg.strip()
            entity_name = entity_query

        print(f"\nQuerying for: Query='{entity_query}', Name='{entity_name}'")
        try:
            results_tuple = load_classifier_value_by_vector_db(
                vector_db=configuration.vector_db,
                collection=full_collection_name,
                embedding_model=configuration.embedding_model,
                entity_query=entity_query,
                classifier_id=args.classifier_id,
                entity_name=entity_name,
                top_k=args.top_k,
                confirm_score=args.confirm_score,
                valid_score=args.valid_score,
                verbose=True # Force verbose to show search process
            )
            
            # load_classifier_value_by_vector_db returns (classifier_value, is_value_confirmed, match_term_id)
            # or (None, False, None) if not found
            classifier_value, is_value_confirmed, match_term_id = results_tuple
            
            if classifier_value:
                status = "Confirmed" if is_value_confirmed else "Unconfirmed (Candidate)"
                print(f"Result: {status}")
                print(f"  Value: {classifier_value.value}")
                print(f"  ID: {classifier_value.id}")
                if match_term_id:
                    print(f"  Match Term ID: {match_term_id}")
            else:
                print("No suitable match found.")

        except Exception as e:
            print(f"Error querying for '{input_arg}': {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
