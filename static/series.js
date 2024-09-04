document.addEventListener('DOMContentLoaded', function() {
    fetchComicsSeries();
});

function fetchComicsSeries() {
    fetch('/comics')
        .then(response => {
            if (!response.ok) {
                throw new Error('网络请求失败');
            }
            return response.json();
        })
        .then(data => {
	    console.log("Received data:", data);
            const series = data.comics;
            const list = document.getElementById('comicsList');
            series.forEach(comicSeries => {
                const item = document.createElement('li');
                const link = document.createElement('a');
                link.href = `/static/comic_reader.html?comic=${encodeURIComponent(comicSeries.id)}`; 
                link.textContent = comicSeries.title;
                item.appendChild(link);
                list.appendChild(item);
            });
        })
        .catch(error => {
            console.error('获取漫画系列失败:', error);
        });
}
