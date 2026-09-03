#!/usr/bin/env bash

set -e

COMMAND="${1:-validate}"

cd databricks

case "$COMMAND" in

    validate)

        databricks bundle validate \
            -t dev

        ;;

    deploy)

        databricks bundle deploy \
            -t dev

        ;;

    prod)

        databricks bundle validate \
            -t prod

        databricks bundle deploy \
            -t prod

        ;;

    *)

        echo "Usage:"
        echo
        echo "  ./scripts/databricks-deploy.sh validate"
        echo "  ./scripts/databricks-deploy.sh deploy"
        echo "  ./scripts/databricks-deploy.sh prod"

        exit 1

        ;;

esac