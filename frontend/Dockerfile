FROM nginx:alpine

# Remove default nginx site
RUN rm -rf /usr/share/nginx/html/*

# Copy web client source files
COPY . /usr/share/nginx/html

# Copy custom nginx configuration to templates directory for automatic envsubst of $PORT
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Default PORT if not provided by runtime
ENV PORT=80

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
