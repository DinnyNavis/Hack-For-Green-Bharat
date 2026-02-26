FROM nginx:1.25-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html        /usr/share/nginx/html/
COPY app.js           /usr/share/nginx/html/
COPY styles.css       /usr/share/nginx/html/
COPY chart.umd.min.js /usr/share/nginx/html/
COPY finlog_monitor.png /usr/share/nginx/html/
EXPOSE 80
