#!/bin/bash
set -e

sudo tee /etc/nginx/sites-available/govfund > /dev/null << 'EOF'
server {
    listen 80;
    server_name 35.188.175.38.nip.io;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }
}
EOF

sudo nginx -t
sudo systemctl reload nginx
