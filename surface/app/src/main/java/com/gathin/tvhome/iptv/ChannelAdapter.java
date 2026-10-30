package com.gathin.tvhome.iptv;

import android.view.KeyEvent;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.gathin.tvhome.R;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class ChannelAdapter extends RecyclerView.Adapter<ChannelAdapter.ViewHolder> {

    public interface OnChannelClickListener {
        void onChannelClick(Channel channel, int position);
    }

    public interface OnChannelFavoriteToggleListener {
        void onFavoriteToggle(Channel channel, int position, boolean isFavorite);
    }

    private final List<Channel> channels = new ArrayList<>();
    private final Set<String> favoriteUrls = new HashSet<>();
    private final OnChannelClickListener listener;
    private OnChannelFavoriteToggleListener favoriteListener;
    private int selectedPosition = -1;

    public ChannelAdapter(OnChannelClickListener listener) {
        this.listener = listener;
    }

    public void setOnFavoriteToggleListener(OnChannelFavoriteToggleListener favoriteListener) {
        this.favoriteListener = favoriteListener;
    }

    public void setFavorites(Set<String> favs) {
        favoriteUrls.clear();
        if (favs != null) {
            favoriteUrls.addAll(favs);
        }
        notifyDataSetChanged();
    }

    public boolean isFavorite(Channel channel) {
        return channel != null && (favoriteUrls.contains(channel.getUrl()) || favoriteUrls.contains(channel.getId()));
    }

    public void toggleFavorite(int position) {
        if (position < 0 || position >= channels.size()) return;
        Channel ch = channels.get(position);
        boolean nowFav;
        String key = ch.getUrl().isEmpty() ? ch.getId() : ch.getUrl();
        if (favoriteUrls.contains(key)) {
            favoriteUrls.remove(key);
            nowFav = false;
        } else {
            favoriteUrls.add(key);
            nowFav = true;
        }
        notifyItemChanged(position);
        if (favoriteListener != null) {
            favoriteListener.onFavoriteToggle(ch, position, nowFav);
        }
    }

    public void setChannels(List<Channel> newChannels) {
        channels.clear();
        if (newChannels != null) {
            channels.addAll(newChannels);
        }
        notifyDataSetChanged();
    }

    public Channel getChannel(int position) {
        if (position >= 0 && position < channels.size()) {
            return channels.get(position);
        }
        return null;
    }

    public int getSelectedPosition() {
        return selectedPosition;
    }

    public void setSelectedPosition(int position) {
        int old = selectedPosition;
        selectedPosition = position;
        if (old >= 0 && old < channels.size()) notifyItemChanged(old);
        if (selectedPosition >= 0 && selectedPosition < channels.size()) notifyItemChanged(selectedPosition);
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_iptv_channel, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        Channel channel = channels.get(position);
        holder.txtIndex.setText(String.format(Locale.ROOT, "#%02d", position + 1));
        holder.txtName.setText(channel.getName());
        
        String country = channel.getCountry();
        String cat = channel.getCategory();
        String meta = cat + (country.isEmpty() ? "" : " • " + country) + " • 1080p";
        holder.txtMeta.setText(meta);

        boolean fav = isFavorite(channel);
        holder.txtFavorite.setVisibility(fav ? View.VISIBLE : View.GONE);

        boolean isCurrent = (position == selectedPosition);
        holder.itemView.setActivated(isCurrent);

        holder.itemView.setOnClickListener(v -> {
            setSelectedPosition(holder.getBindingAdapterPosition());
            if (listener != null) {
                listener.onChannelClick(channel, holder.getBindingAdapterPosition());
            }
        });

        holder.itemView.setOnLongClickListener(v -> {
            toggleFavorite(holder.getBindingAdapterPosition());
            return true;
        });

        holder.itemView.setOnKeyListener((v, keyCode, event) -> {
            if (event.getAction() == KeyEvent.ACTION_DOWN) {
                if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_STAR || keyCode == KeyEvent.KEYCODE_BUTTON_Y) {
                    toggleFavorite(holder.getBindingAdapterPosition());
                    return true;
                }
            }
            return false;
        });

        holder.itemView.setOnFocusChangeListener((v, hasFocus) -> {
            if (hasFocus) {
                v.animate().scaleX(1.02f).scaleY(1.02f).setDuration(120).start();
                com.gathin.tvhome.audio.CyberSoundSynth.get().playDataClick();
            } else {
                v.animate().scaleX(1.0f).scaleY(1.0f).setDuration(120).start();
            }
        });
    }

    @Override
    public int getItemCount() {
        return channels.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        final TextView txtIndex;
        final TextView txtName;
        final TextView txtMeta;
        final TextView txtLive;
        final TextView txtFavorite;

        ViewHolder(View itemView) {
            super(itemView);
            txtIndex = itemView.findViewById(R.id.txtChannelIndex);
            txtName = itemView.findViewById(R.id.txtChannelName);
            txtMeta = itemView.findViewById(R.id.txtChannelMeta);
            txtLive = itemView.findViewById(R.id.txtLiveIndicator);
            txtFavorite = itemView.findViewById(R.id.txtFavoriteStar);
        }
    }
}
